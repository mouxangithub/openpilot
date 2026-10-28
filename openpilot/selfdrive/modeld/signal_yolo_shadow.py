"""Opt-in traffic-light detector observer. Never controls the vehicle.

Runs the YOLOv8 traffic-light detector on the road camera and writes the
observations it produces to a tmpfs transport that the existing signal
consumers can read. It does not decide which lane a signal governs, does not
measure distances and does not grant movement permission; the consumer
decides what a detection means.

The detector is a *replacement* observation producer for the classical colour
observer, not a second opinion on the same frame: both would write to the same
transport. Only one producer may be active at a time, and this one stays off
unless its own opt-in file exists.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

DIRECTORY = Path('/data/signal-yolo-shadow')
ENABLE_PATH = DIRECTORY / 'enabled'
OBSERVATION_PATH = Path('/dev/shm/carrot_signal_yolo_observation.json')
MODEL_PATH = Path('/data/signal-yolo-shadow/signal_light_detector.onnx')
MANIFEST_PATH = DIRECTORY / 'installed.json'

# The model ships in the repository; the observer runs from a copy on the
# device so a later update cannot change the graph under a running observer.
REPO_MODEL = (Path(__file__).resolve().parents[2] /
              'sunnypilot/assets/vision_models/signal_light_detector.onnx')

MODEL_SHA256 = '7fdf89728e86d33e8d4d67902c10804762301cc8c3dc2f28ee168adad5b893fd'
MODEL_CLASSES = ['traffic_light', 'green_light', 'left_light', 'red_light', 'right_light', 'yellow_light']
MODEL_INPUT_SIZE = 416

# Road camera geometries in this fork: the comma 3X (mici, OS04C10) delivers
# 1344x760 road frames and the comma 3 (tici, OX03C10) delivers 1928x1208. The
# detector maps boxes back per-axis and every record carries its own size, so
# both geometries publish self-describing records; anything else is refused
# rather than guessed.
SUPPORTED_SIZES = ((1344, 760), (1928, 1208))
REFERENCE_SIZE = SUPPORTED_SIZES[0]

MAX_OBSERVATION_BYTES = 32768
MAX_INPUT_AGE_MS = 300
# Camera-to-publish bound. The mici path lands around ~100 ms; the comma 3's
# little-core forward is ~400 ms, so the published result always lags its
# frame by more than the old 200 ms and ``fresh`` was structurally false there.
MAX_RESULT_AGE_MS = 1000

# At most two inferences per second with a bounded CPU duty: on the comma 3's
# little cores a 416x416 forward costs ~400 ms wall on two cv2 threads, so the
# 3x-wall duty floor throttles to ~0.6 Hz there while never exceeding ~25% of
# each little core. Faster devices run at the TARGET_HZ cap.
TARGET_HZ = 2.0
TARGET_CPU_DUTY = .25


def requested(directory=DIRECTORY):
  """Opt-in state. Absent file means off; nothing enables this by default."""
  try:
    return (Path(directory) / 'enabled').read_text().strip() == '1'
  except OSError:
    return False


def validate_artifact(directory=DIRECTORY, model_path=MODEL_PATH):
  """Check the installed model against its manifest and checksum."""
  directory = Path(directory)
  manifest = json.loads((directory / 'installed.json').read_text())
  if (manifest.get('version') != 1 or manifest.get('mode') != 'camera_comparison_only' or
      manifest.get('model_sha256') != MODEL_SHA256 or manifest.get('classes') != MODEL_CLASSES or
      manifest.get('input_size') != MODEL_INPUT_SIZE or
      manifest.get('control_permission') is not False):
    raise ValueError('invalid signal-yolo comparison manifest')
  path = Path(model_path)
  if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
    raise ValueError('signal-yolo ONNX checksum mismatch')
  return path, manifest


def install(directory=DIRECTORY, model_path=MODEL_PATH, source_model=REPO_MODEL):
  """Install the model and its manifest into the observer's directory.

  The manifest records that this artifact is a comparison-only observer, so a
  manifest that claims control permission can never be loaded by it. Nothing
  here enables the observer: installing the artifact and running it are
  separate decisions.
  """
  directory = Path(directory)
  directory.mkdir(parents=True, exist_ok=True)
  source_model = Path(source_model)
  if not source_model.is_file():
    raise FileNotFoundError(f'model not found: {source_model}')
  digest = hashlib.sha256(source_model.read_bytes()).hexdigest()
  if digest != MODEL_SHA256:
    raise ValueError('signal-yolo ONNX checksum mismatch')
  model_path = Path(model_path)
  temp = model_path.with_suffix('.tmp')
  temp.write_bytes(source_model.read_bytes())
  temp.replace(model_path)
  manifest = {
    'version': 1,
    'mode': 'camera_comparison_only',
    'model_sha256': digest,
    'classes': MODEL_CLASSES,
    'input_size': MODEL_INPUT_SIZE,
    'control_permission': False,
  }
  manifest_path = directory / 'installed.json'
  temp_manifest = manifest_path.with_suffix('.tmp')
  temp_manifest.write_text(json.dumps(manifest, indent=2))
  temp_manifest.replace(manifest_path)
  return manifest


def next_delay(work_wall):
  """Bound the rate and the CPU duty of one core.

  A slow frame never catches up on queued frames: the observer always waits,
  it never runs two inferences back to back to make up for lost time. The
  duty floor is measured against wall time: the forward runs two cv2 threads
  (see ``build_net``), so at the floor each thread sees ~25% of its core —
  process_time would double-count the threads and idle the observer.
  """
  return max(.05, 1.0 / TARGET_HZ - work_wall, 3 * work_wall)


def configure_worker_scheduling():
  """Pin the worker to the little cores and the lowest priority.

  Linux affinity and nice are per-thread, and the manager's spawn launcher can
  create logging/IPC threads before main() runs, so those existing threads are
  included too.
  """
  allowed = os.sched_getaffinity(0) & {0, 1, 2, 3}
  if not allowed:
    raise RuntimeError('no permitted little CPU for signal observer')
  for task in Path('/proc/self/task').iterdir():
    try:
      tid = int(task.name)
      os.sched_setaffinity(tid, allowed)
      os.sched_setscheduler(tid, os.SCHED_OTHER, os.sched_param(0))
      os.setpriority(os.PRIO_PROCESS, tid, 19)
    except ProcessLookupError:
      pass


def copy_nv12_rgb(frame):
  """Copy the camera's NV12 buffer into an RGB image.

  This is independent of modeld's warp and calibration and does not mutate the
  IPC data. Raw camera versus encoded-video colour differences need separate
  validation.
  """
  import cv2
  import numpy as np
  width, height = int(frame.width), int(frame.height)
  stride, offset = int(frame.stride), int(frame.uv_offset)
  if width <= 0 or height <= 0 or width % 2 or height % 2 or stride < width or stride % 2 or offset < stride * height:
    raise ValueError('invalid NV12 dimensions')
  raw = np.frombuffer(frame.data, np.uint8)
  end = offset + stride * (height // 2)
  if raw.size < end:
    raise ValueError('truncated NV12 buffer')
  packed = np.empty((height * 3 // 2, width), np.uint8)
  packed[:height] = raw[:height * stride].reshape(height, stride)[:, :width]
  packed[height:] = raw[offset:end].reshape(height // 2, stride)[:, :width]
  return cv2.cvtColor(packed, cv2.COLOR_YUV2RGB_NV12)


def publish_observation(record, path=OBSERVATION_PATH):
  """Write the observation atomically, bounded in size."""
  text = json.dumps(record, allow_nan=False)
  if len(text.encode()) > MAX_OBSERVATION_BYTES:
    raise ValueError('signal observation too large')
  path = Path(path)
  temp = path.with_suffix('.tmp')
  temp.write_text(text)
  temp.replace(path)


def build_net(model_path):
  """Load the exported graph through OpenCV's DNN backend.

  OpenCV is already a dependency of this fork, and it is cheaper here than
  ONNX Runtime (69 ms vs 122 ms for one 416x416 forward on the same machine)
  while producing the same detections. Thread count is pinned: the little
  cores are shared with the driving stack, and unbounded cv2 fan-out showed
  ~2.7 threads' worth of CPU per forward on the comma 3.
  """
  import cv2
  cv2.setNumThreads(2)
  net = cv2.dnn.readNetFromONNX(str(model_path))
  net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
  net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
  return net


def run(directory=DIRECTORY, duration=None, model_path=MODEL_PATH, observation_path=OBSERVATION_PATH):
  import fcntl
  directory = Path(directory)
  if not requested(directory):
    return
  directory.mkdir(parents=True, exist_ok=True)
  with (directory / 'worker.lock').open('w') as lock:
    try:
      fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      return
    configure_worker_scheduling()
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
      os.environ[name] = '1'
    from openpilot.cereal.visionipc import VisionStreamType
    from msgq.visionipc import VisionIpcClient
    from openpilot.common.swaglog import cloudlog
    from openpilot.sunnypilot.carrot.signal_yolo_detector import (HousingTracker, detect,
                                                                  observation_record, valid_box)
    path, manifest = validate_artifact(directory, model_path)
    net = build_net(path)
    tracker = HousingTracker()
    client = VisionIpcClient('camerad', VisionStreamType.VISION_STREAM_NARROW_ROAD, True)
    start = time.monotonic()
    session_id = f'{os.getpid()}:{time.monotonic_ns()}'
    cloudlog.event('signalYoloShadowLoaded', **manifest, pid=os.getpid(), target_hz=TARGET_HZ,
                   target_cpu_duty=TARGET_CPU_DUTY, stream='road',
                   supported_sizes=[list(size) for size in SUPPORTED_SIZES])
    previous_id = None
    while requested(directory) and (duration is None or time.monotonic() - start < duration):
      if not client.is_connected() and not client.connect(False):
        time.sleep(1)
        continue
      frame = client.recv(timeout_ms=100)
      if frame is None:
        time.sleep(.1)
        continue
      frame_id, eof = int(client.frame_id), int(client.timestamp_eof)
      if frame_id == previous_id:
        time.sleep(.05)
        continue
      previous_id = frame_id
      work_start, cpu_start = time.monotonic(), time.process_time()
      input_age = (time.monotonic_ns() - eof) / 1e6
      if input_age < 0 or input_age > MAX_INPUT_AGE_MS:
        cloudlog.event('signalYoloShadowSkipped', frame_id=frame_id, timestamp_eof=eof,
                       reason='stale_input', input_age_ms=input_age)
        time.sleep(1)
        continue
      width, height = int(frame.width), int(frame.height)
      if (width, height) not in SUPPORTED_SIZES:
        # An unknown road camera geometry is refused rather than guessed; the
        # two known ones are self-describing in the record.
        cloudlog.event('signalYoloShadowSkipped', frame_id=frame_id, reason='unsupported_camera_geometry',
                       width=width, height=height)
        time.sleep(1)
        continue
      rgb = copy_nv12_rgb(frame)
      if int(frame.frame_id) != frame_id:
        cloudlog.event('signalYoloShadowSkipped', frame_id=frame_id, timestamp_eof=eof,
                       reason='buffer_reused_during_copy')
        time.sleep(1)
        continue
      observations = detect(rgb, net)
      observations = [o for o in observations if valid_box(o.box, width, height)]
      elapsed, cpu = time.monotonic() - work_start, time.process_time() - cpu_start
      age = (time.monotonic_ns() - eof) / 1e6
      record = observation_record(observations, frame_id, eof / 1e9, session_id, width=width, height=height,
                                  tracker=tracker)
      record.update(mode='camera_comparison_only', model_sha256=MODEL_SHA256, stream='road',
                    timestamp_eof=eof, recorded_monotonic_ns=time.monotonic_ns(),
                    input_age_ms=input_age, result_age_ms=age,
                    work_ms=elapsed * 1000, cpu_ms=cpu * 1000,
                    prediction=_overall_state(observations),
                    fresh=0 <= age <= MAX_RESULT_AGE_MS,
                    control_permission=False)
      try:
        publish_observation(record, observation_path)
      except (OSError, ValueError):
        cloudlog.exception('signalYoloObservationPublishFailed')
      cloudlog.event('signalYoloShadow', **record)
      time.sleep(next_delay(elapsed))


def _overall_state(observations):
  """The single agreed colour among the observed housings, else unknown."""
  states = {o.state for o in observations if o.state != 'unknown'}
  return states.pop() if len(states) == 1 else 'unknown'


def main():
  # The manager calls main() without CLI arguments. An unexpected failure
  # exits nonzero so the manager's restart_if_crash re-launches a clean
  # process that re-validates the artifact — a fixed or reinstalled model is
  # picked up without an ignition cycle. A normal return means the observer
  # is off, or another worker holds the lock; hold the idle slot while still
  # requested so the manager does not churn relaunches.
  try:
    run()
  except Exception:
    from openpilot.common.swaglog import cloudlog
    cloudlog.exception('signalYoloShadowCrashed; original control unchanged, manager will relaunch')
    raise SystemExit(1) from None
  while requested():
    time.sleep(1)


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Read-only traffic-light detector observation')
  parser.add_argument('mode', choices=('install', 'on', 'off', 'status', 'run'))
  parser.add_argument('--seconds', type=float)
  args = parser.parse_args()
  if args.mode == 'install':
    print(json.dumps(install(), indent=2))
  if args.mode in ('on', 'off'):
    if args.mode == 'on':
      validate_artifact()
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    temp = DIRECTORY / 'enabled.tmp'
    temp.write_text('1' if args.mode == 'on' else '0')
    temp.replace(DIRECTORY / 'enabled')
  if args.mode == 'run':
    run(duration=args.seconds)
  elif args.mode != 'install':
    print(json.dumps({'requested': requested(), 'control': 'original',
                      'latest': json.loads((OBSERVATION_PATH).read_text()) if OBSERVATION_PATH.exists() else None}))

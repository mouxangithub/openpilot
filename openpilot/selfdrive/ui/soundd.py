import math
import numpy as np
import time
import wave


from openpilot.cereal import log, messaging, custom
from openpilot.common.basedir import BASEDIR
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.realtime import Ratekeeper
from openpilot.common.swaglog import cloudlog

from openpilot.system import micd
from openpilot.common.hardware import HARDWARE

from openpilot.sunnypilot.selfdrive.ui.quiet_mode import QuietMode

SAMPLE_RATE = 48000
SAMPLE_BUFFER = 4096 # (approx 100ms)
MAX_VOLUME = 1.0
MIN_VOLUME = 0.1
ALERT_RAMP_TIME = 4 # seconds to ramp to max volume for warningImmediate
SELFDRIVE_STATE_TIMEOUT = 5 # 5 seconds
MAX_ENGAGED_OUTAGE = 30  # seconds without audio while engaged before we let manager soft disable
FILTER_DT = 1. / (micd.SAMPLE_RATE / micd.FFT_SAMPLES)

AMBIENT_DB = 26 # DB where MIN_VOLUME is applied
DB_SCALE = 30 # AMBIENT_DB + DB_SCALE is where MAX_VOLUME is applied

VOLUME_BASE = 20
if HARDWARE.get_device_type() == "tizi":
  AMBIENT_DB = 30
# rick - for c3
if HARDWARE.get_device_type() in ("tizi", "tici"):
  VOLUME_BASE = 10

AudibleAlert = log.SelfdriveState.AudibleAlert
AudibleAlertSP = custom.SelfdriveStateSP.AudibleAlert


sound_list_sp: dict[int, tuple[str, int | None, float]] = {
  # AudibleAlertSP, file name, play count (none for infinite)
  AudibleAlertSP.promptSingleLow: ("prompt_single_low.wav", 1, MAX_VOLUME),
  AudibleAlertSP.promptSingleHigh: ("prompt_single_high.wav", 1, MAX_VOLUME),
}

sound_list: dict[int, tuple[str, int | None, float]] = {
  # AudibleAlert, file name, play count (none for infinite)
  AudibleAlert.engage: ("engage.wav", 1, MAX_VOLUME),
  AudibleAlert.disengage: ("disengage.wav", 1, MAX_VOLUME),
  AudibleAlert.refuse: ("refuse.wav", 1, MAX_VOLUME),

  AudibleAlert.prompt: ("warning.wav", 1, MAX_VOLUME),
  AudibleAlert.promptRepeat: ("warning.wav", None, MAX_VOLUME),
  AudibleAlert.promptDistracted: ("dm_warning.wav", None, MAX_VOLUME),

  AudibleAlert.preAlert: ("pre_alert.wav", 1, MAX_VOLUME),

  AudibleAlert.warningSoft: ("critical.wav", None, MAX_VOLUME),
  AudibleAlert.warningImmediate: ("dm_critical.wav", None, MAX_VOLUME),

  **sound_list_sp,

  # CarrotPilot audio alerts
  AudibleAlertSP.audioTurn: ("audio_turn.wav", None, MAX_VOLUME),
  AudibleAlertSP.longEngaged: ("tici_engaged.wav", None, MAX_VOLUME),
  AudibleAlertSP.longDisengaged: ("tici_disengaged.wav", None, MAX_VOLUME),
  AudibleAlertSP.trafficSignGreen: ("traffic_sign_green.wav", None, MAX_VOLUME),
  AudibleAlertSP.trafficSignChanged: ("traffic_sign_changed.wav", None, MAX_VOLUME),
  AudibleAlertSP.laneChangeCarrot: ("audio_lane_change.wav", None, MAX_VOLUME),
  AudibleAlertSP.stopping: ("audio_stopping.wav", None, MAX_VOLUME),
  AudibleAlertSP.autoHold: ("audio_auto_hold.wav", None, MAX_VOLUME),
  AudibleAlertSP.engage2: ("audio_engage.wav", None, MAX_VOLUME),
  AudibleAlertSP.disengage2: ("audio_disengage.wav", None, MAX_VOLUME),
  AudibleAlertSP.trafficError: ("audio_traffic_error.wav", None, MAX_VOLUME),
  AudibleAlertSP.bsdWarning: ("audio_car_watchout.wav", None, MAX_VOLUME),
  AudibleAlertSP.speedDown: ("audio_speed_down.wav", None, MAX_VOLUME),
  AudibleAlertSP.stopStop: ("audio_stopstop.wav", None, MAX_VOLUME),
  AudibleAlertSP.reverseGear2: ("reverse_gear.wav", 1, MAX_VOLUME),
  AudibleAlertSP.audio1: ("audio_1.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio2: ("audio_2.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio3: ("audio_3.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio4: ("audio_4.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio5: ("audio_5.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio6: ("audio_6.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio7: ("audio_7.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio8: ("audio_8.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio9: ("audio_9.wav", None, MAX_VOLUME),
  AudibleAlertSP.audio10: ("audio_10.wav", None, MAX_VOLUME),
  AudibleAlertSP.nnff: ("nnff.wav", None, MAX_VOLUME),
  AudibleAlertSP.preLaneChangeCarrot: ("audio_pre_lane_change.wav", None, MAX_VOLUME),
  AudibleAlertSP.atcCancel: ("audio_atc_cancel.wav", None, MAX_VOLUME),
  AudibleAlertSP.atcResume: ("audio_atc_resume.wav", None, MAX_VOLUME),
  AudibleAlertSP.preLaneChangeLeft2: ("audio_pre_lane_left.wav", None, MAX_VOLUME),
  AudibleAlertSP.preLaneChangeRight2: ("audio_pre_lane_right.wav", None, MAX_VOLUME),
  AudibleAlertSP.laneChangeOk: ("audio_lane_change_ok.wav", None, MAX_VOLUME),
  AudibleAlertSP.lastLane: ("audio_last_lane.wav", None, MAX_VOLUME),
  AudibleAlertSP.newLane: ("audio_new_lane.wav", None, MAX_VOLUME),
  AudibleAlertSP.laneChangeEnd: ("audio_lane_change_end.wav", None, MAX_VOLUME),
}

def check_selfdrive_timeout_alert(sm):
  ss_missing = time.monotonic() - sm.recv_time['selfdriveState']

  if ss_missing > SELFDRIVE_STATE_TIMEOUT:
    if (sm['selfdriveState'].enabled or sm['selfdriveStateSP'].mads.enabled) and (ss_missing - SELFDRIVE_STATE_TIMEOUT) < 10:
      return True

  return False


class Soundd(QuietMode):
  def __init__(self):
    super().__init__()

    self.load_sounds()

    self.current_alert = AudibleAlert.none
    self.current_volume = MIN_VOLUME
    self.current_sound_frame = 0

    self.ramp_start_volume = MIN_VOLUME
    self.ramp_start_time = 0.

    self.selfdrive_timeout_alert = False
    self.pending_stop = False

    self.spl_filter_weighted = FirstOrderFilter(0, 2.5, FILTER_DT, initialized=False)

    # CarrotPilot audio state tracking
    self.carrot_alert_prev = None
    self.carrot_left_sec_prev = -1
    self.carrot_atc_type_prev = ""

  def load_sounds(self):
    self.loaded_sounds: dict[int, np.ndarray] = {}

    # Load all sounds
    for sound in sound_list:
      filename, play_count, volume = sound_list[sound]
      path = BASEDIR + "/openpilot/selfdrive/assets/sounds/" + filename

      try:
        with wave.open(path, 'r') as wavefile:
          assert wavefile.getnchannels() == 1
          assert wavefile.getsampwidth() == 2
          assert wavefile.getframerate() == SAMPLE_RATE

          length = wavefile.getnframes()
          self.loaded_sounds[sound] = np.frombuffer(wavefile.readframes(length), dtype=np.int16).astype(np.float32) / (2**16/2)
      except (FileNotFoundError, wave.Error, AssertionError) as e:
        # Never take soundd down for a missing/malformed sound asset.
        cloudlog.error(f"soundd: failed to load sound {filename}: {e}")
        self.loaded_sounds[sound] = np.zeros(int(SAMPLE_RATE * 0.1), dtype=np.float32)

  def get_sound_data(self, frames): # get "frames" worth of data from the current alert sound, looping when required

    ret = np.zeros(frames, dtype=np.float32)

    if self.should_play_sound(self.current_alert):
      num_loops = sound_list[self.current_alert][1]
      sound_data = self.loaded_sounds[self.current_alert]
      written_frames = 0

      current_sound_frame = self.current_sound_frame % len(sound_data)
      loops = self.current_sound_frame // len(sound_data)

      while written_frames < frames and (num_loops is None or loops < num_loops):
        available_frames = sound_data.shape[0] - current_sound_frame
        frames_to_write = min(available_frames, frames - written_frames)
        ret[written_frames:written_frames+frames_to_write] = sound_data[current_sound_frame:current_sound_frame+frames_to_write]
        written_frames += frames_to_write
        self.current_sound_frame += frames_to_write
        current_sound_frame = self.current_sound_frame % len(sound_data)
        loops = self.current_sound_frame // len(sound_data)
        if self.pending_stop and current_sound_frame == 0:
          self.current_alert = AudibleAlert.none
          self.pending_stop = False
          break

    return ret * self.current_volume

  def callback(self, data_out: np.ndarray, frames: int, time, status) -> None:
    if status:
      cloudlog.warning(f"soundd stream over/underflow: {status}")
    data_out[:frames, 0] = self.get_sound_data(frames)

  def update_alert(self, new_alert):
    current_alert_played_once = self.current_alert == AudibleAlert.none or self.current_sound_frame >= len(self.loaded_sounds[self.current_alert])
    # let looping sounds finish the current loop instead of cutting off mid tone
    if new_alert == AudibleAlert.none and self.current_alert != AudibleAlert.none and sound_list[self.current_alert][1] is None:
      if current_alert_played_once:
        self.pending_stop = True
      else:
        self.current_alert = AudibleAlert.none
        self.current_sound_frame = 0
      return
    self.pending_stop = False
    if self.current_alert != new_alert and (new_alert != AudibleAlert.none or current_alert_played_once):
      if new_alert == AudibleAlert.warningImmediate:
        self.ramp_start_volume = self.current_volume
        self.ramp_start_time = time.monotonic()
      self.current_alert = new_alert
      self.current_sound_frame = 0

  def get_audible_alert(self, sm):
    if sm.updated['selfdriveState']:
      new_alert = sm['selfdriveState'].alertSound.raw
      self.update_alert(new_alert)
    elif check_selfdrive_timeout_alert(sm):
      self.update_alert(AudibleAlert.warningImmediate)
      self.selfdrive_timeout_alert = True
    elif self.selfdrive_timeout_alert:
      self.update_alert(AudibleAlert.none)
      self.selfdrive_timeout_alert = False

  def calculate_volume(self, weighted_db):
    volume = ((weighted_db - AMBIENT_DB) / DB_SCALE) * (MAX_VOLUME - MIN_VOLUME) + MIN_VOLUME
    return math.pow(VOLUME_BASE, (np.clip(volume, MIN_VOLUME, MAX_VOLUME) - 1))

  def get_carrot_alert(self, sm):
    if not sm.alive['carrotManSP']:
      return

    carrot_man = sm['carrotManSP']

    if carrot_man.leftSec != self.carrot_left_sec_prev:
      self.carrot_left_sec_prev = carrot_man.leftSec
      if 1 <= carrot_man.leftSec <= 10:
        alert_name = f'audio{carrot_man.leftSec}'
        if hasattr(AudibleAlertSP, alert_name):
          self.update_alert(getattr(AudibleAlertSP, alert_name))

    atc_type = carrot_man.atcType if hasattr(carrot_man, 'atcType') else ""
    if atc_type != self.carrot_atc_type_prev:
      self.carrot_atc_type_prev = atc_type
      if atc_type:
        if "prepare" in atc_type.lower():
          self.update_alert(AudibleAlertSP.preLaneChangeCarrot)
        elif "cancel" in atc_type.lower():
          self.update_alert(AudibleAlertSP.atcCancel)
        elif "resume" in atc_type.lower():
          self.update_alert(AudibleAlertSP.atcResume)

    traffic_state = carrot_man.trafficState if hasattr(carrot_man, 'trafficState') else 0
    if traffic_state == 1:
      self.update_alert(AudibleAlertSP.trafficSignChanged)
    elif traffic_state == 2:
      self.update_alert(AudibleAlertSP.trafficSignGreen)

  def get_stream(self, sd):
    # reload sounddevice to reinitialize portaudio
    sd._terminate()
    sd._initialize()
    return sd.OutputStream(channels=1, samplerate=SAMPLE_RATE, callback=self.callback, blocksize=SAMPLE_BUFFER)

  def soundd_thread(self):
    # sounddevice must be imported after forking processes
    import sounddevice as sd
    micd.patch_sounddevice(sd)

    sm = messaging.SubMaster(['selfdriveState', 'selfdriveStateSP', 'soundPressure', 'carrotManSP'])

    # The audio device can be missing at boot (amp still being configured) or go away mid-drive,
    # and manager never restarts a crashed process, so a raise here is permanent. Retry instead --
    # but only fail open while disengaged. Staying alive and silent while engaged would suppress
    # the processNotRunning SOFT_DISABLE that is the driver's cue to take over.
    outage_start = None

    while True:
      try:
        with self.get_stream(sd) as stream:
          outage_start = None
          rk = Ratekeeper(20)

          # Drop anything buffered before the outage so an engage chime cannot finish
          # playing after the car has already disengaged.
          self.current_alert = AudibleAlert.none
          self.current_sound_frame = 0
          self.pending_stop = False

          cloudlog.info(f"soundd stream started: {stream.samplerate=} {stream.channels=} {stream.dtype=} {stream.device=}, {stream.blocksize=}")
          while stream.active:
            sm.update(0)

            self.load_param()

            # freeze volume during alerts to avoid mic feedback increasing volume
            if sm.updated['soundPressure']:
              self.spl_filter_weighted.update(sm["soundPressure"].soundPressureWeightedDb)
              if self.current_alert == AudibleAlert.none:
                self.current_volume = self.calculate_volume(float(self.spl_filter_weighted.x))

            self.get_audible_alert(sm)
            self.get_carrot_alert(sm)

            # Ramp up immediate warning sound over 4s
            if self.current_alert == AudibleAlert.warningImmediate:
              elapsed = time.monotonic() - self.ramp_start_time
              ramp_vol = float(np.interp(elapsed, [0, ALERT_RAMP_TIME], [self.ramp_start_volume, MAX_VOLUME]))
              self.current_volume = max(self.current_volume, ramp_vol)

            rk.keep_time()

        cloudlog.error("soundd stream went inactive, reopening")
      except Exception:
        cloudlog.exception("soundd stream failed, reopening")

      if outage_start is None:
        outage_start = time.monotonic()

      # No stream, so nothing else is reading these: keep polling to decide whether to fail closed.
      sm.update(0)
      engaged = sm['selfdriveState'].enabled or sm['selfdriveStateSP'].mads.enabled
      outage = time.monotonic() - outage_start
      if engaged and outage > MAX_ENGAGED_OUTAGE:
        cloudlog.error(f"soundd: no audio for {outage:.0f}s while engaged, exiting so manager soft disables")
        return

      time.sleep(micd.STREAM_RETRY_DELAY)


def main():
  s = Soundd()
  s.soundd_thread()


if __name__ == "__main__":
  main()

import asyncio
from dataclasses import dataclass
import struct
import time

from teleoprtc.tracks import TiciVideoStreamTrack

from openpilot.cereal import messaging
from openpilot.common.realtime import DT_MDL
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog


# v4l2 buffer flag marking an encoded keyframe (linux/videodev2.h)
V4L2_BUF_FLAG_KEYFRAME = 0x8

# arbitrary 16-byte UUID identifying openpilot frame-timing SEI messages
TIMING_SEI_UUID = bytes([
  0xa5, 0xe0, 0xc4, 0xa4, 0x5b, 0x6e, 0x4e, 0x1e,
  0x9c, 0x7e, 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc,
])
_SEI_PREFIX = b'\x00\x00\x00\x01\x06\x05\x30' + TIMING_SEI_UUID


@dataclass(frozen=True)
class EncodedVideoFrame:
  data: bytes
  pts: int

  def __bytes__(self) -> bytes:
    return self.data


class LiveStreamVideoStreamTrack(TiciVideoStreamTrack):
  camera_to_sock_mapping = {
    "driver": "livestreamCabinEncodeData",
    "wideRoad": "livestreamWideRoadEncodeData",
    "road": "livestreamNarrowRoadEncodeData",
  }

  def __init__(self, camera_type: str, video_enabled: bool = True):
    super().__init__(camera_type, DT_MDL)

    self._camera_type = camera_type
    self._sock = self._make_sock(camera_type)
    self._pts = 0
    self._t0_ns = time.monotonic_ns()
    self.timing_sei_enabled = False
    self.params = Params()
    self._seen_keyframe = False
    self.video_enabled = video_enabled

  def stop(self) -> None:
    super().stop()
    self._sock = None

  def _make_sock(self, camera_type: str) -> messaging.SubSocket:
    return messaging.sub_sock(self.camera_to_sock_mapping[camera_type], conflate=True)

  def switch_camera(self, camera_type: str) -> None:
    if camera_type not in self.camera_to_sock_mapping:
      cloudlog.warning(f"LiveStreamVideoStreamTrack: unknown camera type {camera_type}")
      return
    cloudlog.warning(f"LiveStreamVideoStreamTrack: switching to {camera_type}")
    self._camera_type = camera_type
    try:
      if self._sock is not None:
        self._sock.close()
    except Exception:
      pass
    self._sock = self._make_sock(camera_type)
    # Decoder needs a fresh IDR after the source H.264 stream changes.
    self._seen_keyframe = False
    self.request_keyframe()

  def enable(self, enabled: bool):
    self.video_enabled = enabled
    if not enabled:
      self._seen_keyframe = False

  def request_keyframe(self) -> None:
    self.params.put("LivestreamRequestKeyframe", True, block=False)

  def _build_frame_data(self, msg) -> bytes:
    encode_data = getattr(msg, msg.which())
    if not self.timing_sei_enabled:
      return encode_data.header + encode_data.data

    idx = encode_data.idx
    sei_nal = _SEI_PREFIX + struct.pack('>4d',
      (idx.timestampEof - idx.timestampSof) / 1e6,
      (msg.logMonoTime - idx.timestampEof) / 1e6,
      (time.monotonic_ns() - msg.logMonoTime) / 1e6,
      time.time() * 1000,  # noqa: TID251
    ) + b'\x80'
    return encode_data.header + sei_nal + encode_data.data

  async def recv(self):
    while True:
      # while video is disabled, pause here without returning
      if not self.video_enabled:
        await asyncio.sleep(0.005)
        continue

      msg = messaging.recv_one_or_none(self._sock)
      if msg is not None:
        is_keyframe = bool(getattr(msg, msg.which()).idx.flags & V4L2_BUF_FLAG_KEYFRAME)
        if not self._seen_keyframe:
          if is_keyframe:
            self._seen_keyframe = True
            self.params.put("LivestreamRequestKeyframe", False, block=False)
          else:
            # After a camera switch the decoder needs a fresh IDR before we
            # send frames from the new H.264 stream; drop inter frames until
            # the requested keyframe arrives.
            await asyncio.sleep(0.005)
            continue
        break
      await asyncio.sleep(0.005)

    self._pts =  ((time.monotonic_ns() - self._t0_ns) * self._clock_rate) // 1_000_000_000
    encode_data = getattr(msg, msg.which())
    is_keyframe = bool(encode_data.idx.flags & V4L2_BUF_FLAG_KEYFRAME)
    cloudlog.warning(
      f"LiveStreamVideoStreamTrack: sending frame camera={self._camera_type} "
      f"pts={self._pts} keyframe={is_keyframe} data_len={len(encode_data.data)} "
      f"header_len={len(encode_data.header)} width={encode_data.width} height={encode_data.height}"
    )

    return EncodedVideoFrame(self._build_frame_data(msg), self._pts)

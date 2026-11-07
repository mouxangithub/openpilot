"""
Copyright (c) 2026-, Zeph Leggett.

This file is part of jetlink and is licensed under the MIT License.
See the LICENSE file in the root directory for more details.

How a frame is carried: the negotiation, and the codec that puts the warped
frame on the wire.

The wire has always carried the warped frame one of two ways: raw, 393,304
bytes for a big model's (2, 6, 128, 256) uint8, or lossless-packed, about half
that (jetlink.lossless). Both are bit-for-bit, and both are sized for USB 3 and
for a good Wi-Fi link respectively. Neither helps where the reference fork
sends frames: a phone on a hotel Wi-Fi, or a comma on LTE tethering, where
393 KB a frame at 20 Hz is 63 Mbit/s and no amount of prediction gets there.

So a third carrier exists, HEVC: the warped frame goes through the comma's
Venus hardware encoder (the one loggerd already uses), 2 Mb/s a second per
camera, about 8 KB a frame at the model's 512x256. It is lossy, and it is the
only carrier whose outputs are not bit-for-bit with the raw frame, so it is
never chosen automatically: a server offers it, and the comma takes it only
where the user has said the loss is acceptable (a link slow enough that the
alternative is no big model at all).

The negotiation is the server's hello list, `frame_codecs`, and this module is
the comma's half of it: the names, what each costs, and which one to pick. A
server that lists nothing is a server from before this existed, and gets raw
frames exactly as it always did.

The encoder itself is a seam (HEVCEncoder): the comma's Venus encoder is a
device only, so the interface here is what the frame path depends on and the
implementations live where their hardware is.
"""
from __future__ import annotations

from dataclasses import dataclass

# The names on the wire, in the server's `frame_codecs`. Raw is never listed:
# it is what every server that has ever existed takes, so a hello without it
# means raw, and listing it would be a promise about nothing
RAW = 'raw'
LOSSLESS = 'med-zstd'      # jetlink.lossless; also protocol.LOSSLESS_CODEC
HEVC = 'hevc'              # the Venus hardware encoder, 512x256 in, Annex-B out

# every name a server may list, and every name a client understands
CODECS = (LOSSLESS, HEVC)

# What each codec costs, for the pick and for the log. Bytes are the steady
# state a frame reaches, per camera, at the model's 512x256; the raw figure is
# exact (a big model's warped_shape), the others measured on a drive
RAW_BYTES = 196608            # 6 planes of 128x256, per camera
LOSSLESS_RATIO = 2.1          # route 286, 2026-10-06 (jetlink.lossless)
HEVC_BYTES = 4096             # 2 Mb/s a camera at 20 Hz (the reference fork)
# bit/s per camera the HEVC carrier was tuned at and its limits: below 1 Mb/s
# the model's lane lines smear, above 8 Mb/s the frame no longer fits a Wi-Fi
# link's own jitter without the hold window eating it
HEVC_DEFAULT_BITRATE = 2_000_000
HEVC_MIN_BITRATE = 1_000_000
HEVC_MAX_BITRATE = 8_000_000
# HEVC Main, no B frames (the frame path is strictly in order and a B frame
# would hold two frames' latency), a GOP of 20 as the reference fork uses
HEVC_GOP = 20


@dataclass(frozen=True)
class Offer:
  """What a codec choice is worth, for the log and for the panels."""
  name: str
  bytes_per_frame: int     # per camera, steady state
  lossless: bool


def offers(hello: dict | None) -> list[str]:
  """The codec names a server's hello lists, in a stable order, unknown names
  dropped. A hello with no list, or one that is not a list, offers raw alone
  (the empty list), which is every server from before the list existed."""
  listed = (hello or {}).get('frame_codecs')
  if not isinstance(listed, list):
    return []
  seen = [name for name in CODECS if name in listed]
  return seen


def cost(name: str, *, raw_bytes: int = RAW_BYTES, hevc_bitrate: int = HEVC_DEFAULT_BITRATE) -> Offer:
  """What carrying frames as `name` costs, per camera a frame."""
  if name == HEVC:
    return Offer(HEVC, max(1, hevc_bitrate // 20 // 8), lossless=False)
  if name == LOSSLESS:
    return Offer(LOSSLESS, int(raw_bytes / LOSSLESS_RATIO), lossless=True)
  return Offer(RAW, raw_bytes, lossless=True)


def pick(hello: dict | None, *, prefer_lossy: bool, raw_bytes: int = RAW_BYTES,
         hevc_bitrate: int = HEVC_DEFAULT_BITRATE) -> str:
  """Which codec to send this server's frames with.

  `prefer_lossy` is the user's: with it off, the answer is the cheapest
  lossless carrier the server offers (lossless over raw), and HEVC is never
  returned even where the server offers it. With it on, HEVC wins whenever the
  server offers it and the link would otherwise be short of the frame budget.

  The rule with it on is deliberately not "HEVC always": a server that offers
  HEVC over USB 3 does not need it, and the raw frame is the better answer
  there. HEVC is picked when the loss is the price of a working link, which is
  a decision about the link, and the caller here knows what it dialed.
  """
  listed = offers(hello)
  if prefer_lossy and HEVC in listed:
    return HEVC
  if LOSSLESS in listed:
    return LOSSLESS
  return RAW


def describe(name: str, *, raw_bytes: int = RAW_BYTES, hevc_bitrate: int = HEVC_DEFAULT_BITRATE) -> str:
  """One line for the log: what this link carries a frame as, and how big."""
  offer = cost(name, raw_bytes=raw_bytes, hevc_bitrate=hevc_bitrate)
  kind = 'lossy' if not offer.lossless else 'lossless'
  return f"{name} ({kind}, ~{offer.bytes_per_frame >> 10} KB/camera/frame)"


class HEVCEncoder:
  """The comma's hardware HEVC encoder, as the frame path uses it.

  A frame in, one Annex-B access unit out. Two cameras are two instances: the
  reference fork runs them as two sessions because a single Venus session
  encoding two independent views costs a reconfiguration each frame, and the
  model's own layout has them as one (2, 6, H, W) image either way.

  The encoder is stateful across frames (GOP, reference pictures, rate
  control), so an instance belongs to one stream: it must be reset when the
  stream restarts (a new connection, or a gap the receiver was told about), or
  the receiver's decoder is left with references it never saw.

  Only the device has an implementation (the Venus V4L2 encoder behind
  loggerd's `logger_lib`); this is the interface, so the frame path, the
  negotiation and the tests never depend on the hardware being there.
  """

  def configure(self, *, width: int, height: int, bitrate: int = HEVC_DEFAULT_BITRATE,
                gop: int = HEVC_GOP) -> None:
    """Set the geometry and the rate control. Called before the first frame and
    again when the bitrate changes; may be called with the same values, and
    then does nothing."""
    raise NotImplementedError

  def encode(self, frame, *, force_keyframe: bool = False) -> tuple[bytes, bool]:
    """One frame's access unit, and whether it came out a keyframe (IDR).

    `frame` is the warped, venus-aligned NV12 of one camera. `force_keyframe`
    asks for an IDR on this frame: the caller sets it when the receiver must
    have one (a new stream, a gap), and reads the returned flag rather than
    assuming it was honoured. The returned bytes are Annex-B, header included
    on a keyframe, valid until the next encode().
    """
    raise NotImplementedError

  def reset(self) -> None:
    """Drop the stream state (references, GOP phase) without reconfiguring:
    the next encoded frame is an IDR and a receiver that has forgotten
    everything can decode from it."""
    raise NotImplementedError

  def close(self) -> None:
    """Release the encoder. Idempotent."""
    raise NotImplementedError

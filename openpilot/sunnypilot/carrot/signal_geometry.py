"""Camera geometry for the signal supervision chain.

The signal geometry used to be written against one hardcoded road-camera
frame: 1344x760 pixels at focal 1141.5 (the comma 3X's OS04C10 narrow road
camera, downsampled from the sensor's native 2688x1520). Every pixel window,
every normalized position, the frame centre and the focal length were
assumed to be that camera's, so the whole chain only ever ran on it - and on
the comma 3 (OX03C10, 1928x1208) every observation was rejected.

This module maps any supported road camera onto that reference frame so the
rest of the chain can stay written in reference pixels.

The mapping is **angular**, not resolution-based. A length of L pixels on a
camera with focal f subtends ``L/f`` radians, so the same physical extent is
``L * REFERENCE_FOCAL / f`` reference pixels. Scaling by the resolution ratio
(1928/1344) would be wrong: the 3X sees 60.97 deg horizontally while the comma
3 sees 40.01 deg, so the same object covers a different *fraction* of each
frame. Carrying the angular scale keeps every existing constant physically
meaningful and leaves the 3X bit-for-bit unchanged (its scale factor is 1.0).

Because the mapping is a pure offset-from-centre scaling, the reference
frame's centre, focal length and frame bounds stay valid for every camera:
a box converted into reference pixels can be handed to the unchanged geometry
code, which then reasons about angles rather than pixels.
"""
from dataclasses import dataclass

# The reference frame: the comma 3X narrow road camera as the chain has
# always seen it. Every threshold in the chain is expressed in these pixels.
REFERENCE_WIDTH = 1344
REFERENCE_HEIGHT = 760
REFERENCE_FOCAL = 1141.5

# The comma 3 (OX03C10) narrow road camera.
C3_WIDTH = 1928
C3_HEIGHT = 1208
C3_FOCAL = 2648.0


@dataclass(frozen=True)
class SignalGeometry:
  """One road camera's frame and its mapping onto the reference frame.

  ``scale`` is reference pixels per camera pixel - the angular scale factor.
  ``focal`` is this camera's own focal length, kept for callers that need it
  directly rather than through the reference frame.
  """
  width: int
  height: int
  focal: float

  def __post_init__(self):
    if self.width <= 0 or self.height <= 0 or self.focal <= 0:
      raise ValueError('invalid signal camera geometry')

  @property
  def size(self) -> tuple[int, int]:
    return (self.width, self.height)

  @property
  def scale(self) -> float:
    """Reference-frame pixels per pixel of this camera."""
    return REFERENCE_FOCAL / self.focal

  @property
  def center(self) -> tuple[float, float]:
    """Image centre in this camera's pixels."""
    return (self.width / 2., self.height / 2.)

  def to_reference(self, value: float) -> float:
    """Scale a length in this camera's pixels into reference pixels."""
    return value * self.scale

  def to_reference_box(self, box) -> tuple[float, float, float, float]:
    """Map a box on this camera into reference-frame pixels.

    The offset from the image centre is scaled angularly, so the box keeps
    its true angular position and extent. The result is expressed in the
    reference frame's pixel coordinates, which is what the unchanged geometry
    code expects: the reference centre (672, 380), the reference focal
    (1141.5) and the reference bounds (1344x760) all stay correct.

    A box outside this camera's frame maps outside the reference frame's
    *angular* coverage - that is expected and not an error, because the two
    cameras do not see the same width.
    """
    x1, y1, x2, y2 = (float(v) for v in box)
    scale = self.scale
    cx, cy = self.center
    ref_cx, ref_cy = REFERENCE_WIDTH / 2., REFERENCE_HEIGHT / 2.
    return (ref_cx + (x1 - cx) * scale, ref_cy + (y1 - cy) * scale,
            ref_cx + (x2 - cx) * scale, ref_cy + (y2 - cy) * scale)


def geometry_for_size(width: int, height: int) -> SignalGeometry | None:
  """The geometry of a road camera that delivers frames of this size.

  Only the two narrow road cameras this fork supports are known here. An
  unknown frame size is refused rather than guessed: a wrong focal length
  would silently corrupt every distance estimate downstream.
  """
  if (width, height) == (REFERENCE_WIDTH, REFERENCE_HEIGHT):
    return SignalGeometry(REFERENCE_WIDTH, REFERENCE_HEIGHT, REFERENCE_FOCAL)
  if (width, height) == (C3_WIDTH, C3_HEIGHT):
    return SignalGeometry(C3_WIDTH, C3_HEIGHT, C3_FOCAL)
  return None


def geometry_for_camera(camera_config) -> SignalGeometry | None:
  """The geometry of a device camera config's narrow road camera."""
  if camera_config is None:
    return None
  narrow = getattr(camera_config, 'narrow_road', None)
  if narrow is None:
    return None
  width, height = narrow.size
  focal = float(narrow.focal_length)
  if width <= 0 or height <= 0 or focal <= 0:
    return None
  return SignalGeometry(width, height, focal)


def to_reference_tracks(tracks, geometry: SignalGeometry | None) -> list:
  """Map every track's box into reference-frame pixels.

  The reference frame is expressed as a list, so the unchanged consumer code
  can keep treating the observation as if it came from the 3X camera. A
  ``None`` geometry means the observation's frame size is unknown; the tracks
  are then passed through untouched and the caller refuses the observation.
  """
  if geometry is None:
    return list(tracks)
  mapped = []
  for track in tracks:
    try:
      box = geometry.to_reference_box(track['box'])
    except (KeyError, TypeError, ValueError):
      mapped.append(track)
      continue
    mapped.append(dict(track, box=list(box)))
  return mapped

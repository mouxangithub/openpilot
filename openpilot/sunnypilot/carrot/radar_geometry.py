"""Geometry constants shared by the radar/vision lead pipeline.

These are deliberately dependency-free (no numpy, capnp or cereal) so both the
control-side helpers and the carrot function library can import them without
pulling in the controls package. The radar's measurement origin sits ahead of
the camera/mesh frame by this distance; a model lead's ``leadsV3.x`` is in the
radar frame and must have it removed to line up with a radar lead's ``dRel``.

Offline replay tools keep their own literal copies (they deliberately do not
import the live tree); change the value in both places together and the guard
test (``test_radar_geometry_constants``) enforces they agree.
"""

# Forward offset, in metres, from the camera/mesh frame centre to the radar
# measurement origin. One physical constant, one source: it used to be copied
# into several production modules, which let them drift apart silently.
RADAR_TO_CAMERA_M = 1.52

"""Deceleration-reason taxonomy for the carrot speed sources.

Ported from CarrotPilot's ``selfdrive/carrot/deceleration_source.py``. This fork
publishes ``carrotManSP.desiredSource`` with exactly the same labels upstream uses
(``atc``/``atc2``/``sdi``-family/``hda``/``hda_bump``/``hda_section``/``road``/
``route``/``school``/``vturn``), but had no mapping from those internal labels to
something a driver can read. The webui printed the raw token; these helpers turn
it into a reason plus a colour class.

Kept as a module rather than inline constants so the taxonomy has one home: the
label set is shared by the display, the diagnostics and any future consumer.
"""

# Sources driven by the phone/navigation app rather than the car's own CAN.
EXTERNAL_NAVI_SOURCES = frozenset((
  "cam", "section", "bump", "police", "waze", "road", "atc", "atc2", "route",
  # This fork's alias for the phone's speed-camera advisory; upstream calls it "cam".
  "sdi",
))
# Sources derived from the vehicle's own navigation CAN (Hyundai 0x4BE family).
VEHICLE_NAVI_SOURCES = frozenset(("hda", "hda_section", "hda_bump", "school"))

DECELERATION_SOURCE_LABELS = {
  "cam": "cam",
  "section": "section",
  "bump": "bump",
  "police": "police",
  "waze": "waze",
  "road": "road",
  "atc": "turn",
  "atc2": "turn",
  "route": "route",
  "hda": "cam",
  "hda_section": "section",
  "hda_bump": "bump",
  "school": "school",
  "gas": "gas",
  "vturn": "vturn",
  "model": "model",
  "turn": "turn",
  # This fork's own display-only tokens, assigned directly to `desired_source` in
  # carrot_serv's cruise-advisory chain (sdi -> turn -> limit). Upstream expresses
  # the same three cases through the speed_n_sources labels above, so these names
  # exist only here.
  "sdi": "cam",
  "limit": "road",
}

# Colour modes used by the HUD to distinguish why the car is slowing.
COLOR_APPLY = 2      # normal deceleration (amber)
COLOR_VEHICLE_NAVI = 3   # vehicle CAN navigation (distinct tint)
COLOR_EXTERNAL_NAVI = 4  # phone / external navigation (distinct tint)


def is_vehicle_navigation_source(source: str | None) -> bool:
  normalized = str(source or "").strip().lower()
  return normalized in VEHICLE_NAVI_SOURCES or normalized in ("cam:v", "bump:v", "school:v")


def deceleration_source_presentation(source: str | None) -> tuple[str, int]:
  """Return the actual deceleration reason and its source colour mode.

  Suffix convention used by the caller's labels:
    ``:n`` external navigation, ``:v`` vehicle CAN navigation, ``:c`` camera.
  An unknown token is passed through trimmed rather than dropped, so a new source
  still shows something instead of silently rendering empty.
  """
  normalized = str(source or "").strip().lower()
  if not normalized:
    return "apply", COLOR_APPLY
  if is_vehicle_navigation_source(normalized):
    return DECELERATION_SOURCE_LABELS.get(normalized, normalized[:8]), COLOR_VEHICLE_NAVI
  if normalized in EXTERNAL_NAVI_SOURCES or normalized.endswith(":n"):
    base = normalized.removesuffix(":n")
    return DECELERATION_SOURCE_LABELS.get(base, base[:8]), COLOR_EXTERNAL_NAVI
  if normalized.endswith(":v"):
    base = normalized.removesuffix(":v")
    mode = COLOR_VEHICLE_NAVI if base in ("cam", "section", "bump", "school") else COLOR_APPLY
    return DECELERATION_SOURCE_LABELS.get(base, base[:8]), mode
  if normalized.endswith(":c"):
    base = normalized.removesuffix(":c")
    return DECELERATION_SOURCE_LABELS.get(base, base[:8]), COLOR_APPLY
  return DECELERATION_SOURCE_LABELS.get(normalized, normalized[:8]), COLOR_APPLY


def navigation_status_presentation(vehicle_available: bool, external_active: bool) -> tuple[str, int] | None:
  """Return the navigation availability badge, independent of speed control."""
  if external_active:
    return "NAVI", COLOR_EXTERNAL_NAVI
  if vehicle_available:
    return "vNAVI", COLOR_VEHICLE_NAVI
  return None


def external_navigation_connected(legacy_remote: str | None, carrot_navi_connected: bool) -> bool:
  """Return external-navigation connectivity without consulting speed-control state."""
  return bool(str(legacy_remote or "").strip()) or bool(carrot_navi_connected)

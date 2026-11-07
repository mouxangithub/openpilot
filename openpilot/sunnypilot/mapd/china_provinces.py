"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

PRC level-1 administrative divisions for the OSM offline map downloader.

Why this lives here, not in mapd's nation_bounding_boxes.json:
  Upstream pfeiferj/mapd v1.12.0 (the binary sunnypilot ships) only knows about
  countries and US states. There is no built-in concept of a "Chinese province".
  Rather than fork the binary or stand up a custom download menu, we exploit
  mapd v1's existing OSMDownloadBounds escape hatch — when that param is set to
  a single Bounds JSON, mapd downloads exactly that bbox and labels it "CUSTOM".
  See https://github.com/pfeiferj/mapd/blob/v1.12.0/download.go.

So this module is consumed in two places:
  1. selfdrive/ui/sunnypilot/layouts/settings/osm.py — populates the province
     selector dialog when the user picks China as the country.
  2. sunnypilot/mapd/mapd_manager.py — translates the selected province ref
     into an OSMDownloadBounds JSON write right before triggering mapd.

Bounding boxes were sourced from the cn-mazda frogpilot fork's curated
mapd_download_menu.json (each province widened to a generous rectangle that
encloses the OSM admin_level=4 boundary). mapd quantises every bbox to 1°
tiles via GROUP_AREA_BOX_DEGREES, so sub-degree precision here is irrelevant.

Note on Taiwan: mapd's stock nation menu already exposes "TW" as a top-level
country, so it is reachable from the existing Country picker without going
through this list. It is also included here for completeness so users who
think of it as a province can find it under China. The two paths download
slightly different bboxes (the entry below is wider than mapd's stock TW
bbox), but both cover the island; pick whichever fits your mental model.
"""


CHINA_NATION_REF = "CN"
CHINA_ALL_REF = "All"


def _compute_china_bbox() -> dict[str, float]:
  """Union of all province bboxes; used for the 'All provinces' download option."""
  if not CHINA_PROVINCES:
    return {}
  return {
    "min_lon": min(bbox["min_lon"] for _, _, bbox in CHINA_PROVINCES),
    "min_lat": min(bbox["min_lat"] for _, _, bbox in CHINA_PROVINCES),
    "max_lon": max(bbox["max_lon"] for _, _, bbox in CHINA_PROVINCES),
    "max_lat": max(bbox["max_lat"] for _, _, bbox in CHINA_PROVINCES),
  }


# (ref, display_name, bbox)
# - ref: ISO 3166-2 code suffix (e.g. "BJ" for CN-BJ) or CHINA_ALL_REF. Used as
#   TreeNode ref and stored in the OsmStateName param so the existing osm.py UI
#   flow can reuse its state-selection plumbing for provinces.
# - display_name: Hanyu Pinyin (no tone marks) to avoid CJK font fallback issues.
# - bbox: covers the province with a ~0.5° safety margin. mapd v1 quantises to
#   1° tiles, so this is intentionally generous.
CHINA_PROVINCES: list[tuple[str, str, dict[str, float]]] = [
  # Direct-administered municipalities
  ("BJ", "Beijing",       {"min_lon": 115.42, "min_lat": 39.44, "max_lon": 117.50, "max_lat": 41.06}),
  ("TJ", "Tianjin",       {"min_lon": 116.71, "min_lat": 38.55, "max_lon": 118.06, "max_lat": 40.25}),
  ("SH", "Shanghai",      {"min_lon": 120.85, "min_lat": 30.68, "max_lon": 122.20, "max_lat": 31.88}),
  ("CQ", "Chongqing",     {"min_lon": 105.29, "min_lat": 28.16, "max_lon": 110.20, "max_lat": 32.20}),

  # North China provinces
  ("HE", "Hebei",         {"min_lon": 113.45, "min_lat": 36.05, "max_lon": 119.85, "max_lat": 42.62}),
  ("SX", "Shanxi",        {"min_lon": 110.22, "min_lat": 34.58, "max_lon": 114.58, "max_lat": 40.74}),

  # Northeast provinces
  ("LN", "Liaoning",      {"min_lon": 118.83, "min_lat": 38.72, "max_lon": 125.78, "max_lat": 43.43}),
  ("JL", "Jilin",         {"min_lon": 121.63, "min_lat": 40.86, "max_lon": 131.31, "max_lat": 46.30}),
  ("HL", "Heilongjiang",  {"min_lon": 121.18, "min_lat": 43.43, "max_lon": 135.09, "max_lat": 53.56}),

  # East China provinces
  ("JS", "Jiangsu",       {"min_lon": 116.36, "min_lat": 30.76, "max_lon": 121.95, "max_lat": 35.12}),
  ("ZJ", "Zhejiang",      {"min_lon": 118.02, "min_lat": 27.04, "max_lon": 123.00, "max_lat": 31.18}),
  ("AH", "Anhui",         {"min_lon": 114.90, "min_lat": 29.41, "max_lon": 119.65, "max_lat": 34.65}),
  ("FJ", "Fujian",        {"min_lon": 115.84, "min_lat": 23.55, "max_lon": 120.72, "max_lat": 28.32}),
  ("JX", "Jiangxi",       {"min_lon": 113.57, "min_lat": 24.49, "max_lon": 118.47, "max_lat": 30.08}),
  ("SD", "Shandong",      {"min_lon": 114.80, "min_lat": 34.38, "max_lon": 122.71, "max_lat": 38.40}),
  ("TW", "Taiwan",        {"min_lon": 119.31, "min_lat": 21.90, "max_lon": 122.07, "max_lat": 26.39}),

  # Central China provinces
  ("HA", "Henan",         {"min_lon": 110.36, "min_lat": 31.39, "max_lon": 116.65, "max_lat": 36.37}),
  ("HB", "Hubei",         {"min_lon": 108.36, "min_lat": 29.03, "max_lon": 116.13, "max_lat": 33.27}),
  ("HN", "Hunan",         {"min_lon": 108.78, "min_lat": 24.64, "max_lon": 114.26, "max_lat": 30.13}),

  # South China provinces / SARs
  ("GD", "Guangdong",     {"min_lon": 109.66, "min_lat": 20.21, "max_lon": 117.31, "max_lat": 25.52}),
  ("GX", "Guangxi",       {"min_lon": 104.46, "min_lat": 20.90, "max_lon": 112.06, "max_lat": 26.39}),
  ("HI", "Hainan",        {"min_lon": 108.62, "min_lat": 17.96, "max_lon": 111.05, "max_lat": 20.16}),
  ("HK", "Xianggang",     {"min_lon": 113.83, "min_lat": 22.15, "max_lon": 114.51, "max_lat": 22.57}),
  ("MO", "Aomen",         {"min_lon": 113.52, "min_lat": 22.10, "max_lon": 113.60, "max_lat": 22.22}),

  # Southwest provinces / autonomous region
  ("SC", "Sichuan",       {"min_lon":  97.35, "min_lat": 26.05, "max_lon": 108.55, "max_lat": 34.32}),
  ("GZ", "Guizhou",       {"min_lon": 103.61, "min_lat": 24.62, "max_lon": 109.62, "max_lat": 29.22}),
  ("YN", "Yunnan",        {"min_lon":  97.53, "min_lat": 21.14, "max_lon": 106.20, "max_lat": 29.23}),
  ("XZ", "Xizang",        {"min_lon":  78.40, "min_lat": 26.85, "max_lon":  99.13, "max_lat": 36.50}),

  # Northwest provinces / autonomous regions
  ("SN", "Shaanxi",       {"min_lon": 105.49, "min_lat": 31.71, "max_lon": 111.25, "max_lat": 39.59}),
  ("GS", "Gansu",         {"min_lon":  92.13, "min_lat": 32.59, "max_lon": 108.71, "max_lat": 42.80}),
  ("QH", "Qinghai",       {"min_lon":  89.35, "min_lat": 31.60, "max_lon": 103.07, "max_lat": 39.21}),
  ("NX", "Ningxia",       {"min_lon": 104.28, "min_lat": 35.24, "max_lon": 107.66, "max_lat": 39.39}),
  ("XJ", "Xinjiang",      {"min_lon":  73.45, "min_lat": 34.34, "max_lon":  96.40, "max_lat": 49.18}),

  # Inner Mongolia autonomous region
  ("NM", "Neimenggu",     {"min_lon":  97.17, "min_lat": 37.40, "max_lon": 126.07, "max_lat": 53.34}),
]


CHINA_PROVINCES_WITH_ALL: list[tuple[str, str, dict[str, float]]] = [
  (CHINA_ALL_REF, "All provinces", _compute_china_bbox()),
  *CHINA_PROVINCES,
]

_BY_REF: dict[str, tuple[str, dict[str, float]]] = {ref: (name, bbox) for ref, name, bbox in CHINA_PROVINCES_WITH_ALL}


def get_province_bbox(ref: str) -> dict[str, float] | None:
  """Return the bounding box dict for a province ref, or None if unknown."""
  entry = _BY_REF.get(ref)
  return entry[1] if entry else None


def get_province_name(ref: str) -> str | None:
  """Return the pinyin display name for a province ref, or None if unknown."""
  entry = _BY_REF.get(ref)
  return entry[0] if entry else None

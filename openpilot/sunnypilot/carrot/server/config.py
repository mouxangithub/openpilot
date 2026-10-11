"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Configuration for the carrot API server."""

import os

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 7000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# carrot/server -> carrot
ROOT_DIR = os.path.dirname(BASE_DIR)

# CarrotPilot's tuning catalog (names, groups, ranges, labels) that drives the settings page.
# Copied from selfdrive/carrot_settings.json; CARROT_SETTINGS_PATH overrides it.
# The fork's own build of CarrotPilot's settings catalog: its menu tree, labels and ranges
# with the params this fork does not declare removed and its own carrot params added.
# Regenerate with `python -m openpilot.sunnypilot.carrot.tools.build_settings_catalog`.
# Serving this one file is what keeps the panel, the setting profiles, the popular-value
# upload and the intro presets on a single catalog.
DEFAULT_SETTINGS_PATH = os.environ.get(
  "CARROT_SETTINGS_PATH",
  os.path.join(os.path.dirname(ROOT_DIR), "carrot_settings_sp.json"),
)


# The web panel. CarrotPilot serves its front end from the same port by adding this tree as
# a static route at "/"; the bundles under js/ and css/ are committed upstream, so the
# device needs no Node at runtime. See docs/carrot-port-parity.md §6 for what is and is not
# reachable from it here.
WEB_DIR = os.path.join(ROOT_DIR, "web")

# Icons and fonts the panel and the cluster share (openpilot/selfdrive/assets).
SELFDRIVE_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(ROOT_DIR)), "selfdrive", "assets")
TRAINING_ASSETS_DIR = os.path.join(SELFDRIVE_ASSETS_DIR, "training")
OFFROAD_ASSETS_DIR = os.path.join(SELFDRIVE_ASSETS_DIR, "offroad")
SOUND_ASSETS_DIR = SELFDRIVE_ASSETS_DIR

# CarrotPilot's launcher can hand the web server off to an external launcher
# (`CARROT_WEB_EXTERNAL=1`); the manager then must not start this process.
CARROT_WEB_EXTERNAL = os.getenv("CARROT_WEB_EXTERNAL") == "1"

# Core affinity for the server. Same default as CarrotPilot: share the background core
# pool rather than the realtime control core (4, which card/controlsd/selfdrived own).
DEFAULT_CORES = (0, 1, 2, 3)


def _state_root() -> str:
  """Where the server keeps its own state.

  CarrotPilot uses `/data/carrot/state`, and anything that reads this device through the
  same app expects to find it there, so the layout is kept. On a development host
  `/data` does not exist and is not writable, so the tree falls back to the temp dir
  rather than having every write fail silently and every read report "empty".
  """
  override = os.getenv("CARROT_DATA_DIR")
  if override:
    return os.path.join(override, "state")
  if os.path.isdir("/data"):
    return "/data/carrot/state"
  return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")


CARROT_STATE_DIR = _state_root()
CARROT_WEB_SETTINGS_PATH = os.path.join(CARROT_STATE_DIR, "web_settings.json")
CARROT_SETTING_FAVORITES_PATH = os.path.join(CARROT_STATE_DIR, "setting_favorites.json")
CARROT_SETTING_PROFILES_PATH = os.path.join(CARROT_STATE_DIR, "setting_profiles.json")
CARROT_SETTING_UNIT_INDEX_PATH = os.path.join(CARROT_STATE_DIR, "setting_unit_index.json")
CARROT_PARAM_CHANGES_PATH = os.path.join(CARROT_STATE_DIR, "param_changes.jsonl")
CARROT_FINGERPRINT_BASELINE_PATH = os.path.join(CARROT_STATE_DIR, "fingerprint_baseline.json")
CARROT_SSH_KEYS_PATH = os.path.join(CARROT_STATE_DIR, "ssh_keys.json")
CARROT_MAPBOX_TOKENS_PATH = os.path.join(CARROT_STATE_DIR, "mapbox_tokens.json")
CARROT_INTRO_STATE_PATH = os.path.join(CARROT_STATE_DIR, "intro.json")

# Where a full parameter dump is written so it can be downloaded straight off the device.
PARAMS_BACKUP_PATH = "/data/media/params_backup.json" if os.path.isdir("/data/media") else os.path.join(CARROT_STATE_DIR, "params_backup.json")
# CarrotPilot ports this fork now serves fully (dashcam / screenrecord / terminal / tools).

# Dashcam
DASHCAM_ROOT = "/data/media/0/realdata"
DASHCAM_CACHE_DIR = os.path.join(CARROT_STATE_DIR, "cache", "dashcam")
CARROT_DASHCAM_READ_STATE_PATH = os.path.join(CARROT_STATE_DIR, "dashcam_read_state.json")

# Screen recording
SCREEN_RECORDING_DIRS = (
  "/data/media/0/videos",
  "/data/media/0/screenrecord",
  "/data/media/0/screen_recordings",
  "/data/media/0/screenrecords",
  "/data/media/0/ScreenRecords",
  "/data/media/0/Movies",
  "/sdcard/Movies",
)
SCREEN_RECORDING_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".ts", ".hevc")

# Git / tool jobs state (kept in the carrot state dir, outside the working tree)
CARROT_GIT_STATE_PATH = os.path.join(CARROT_STATE_DIR, "git.json")
CARROT_TOOL_JOBS_STATE_PATH = os.path.join(CARROT_STATE_DIR, "tool_jobs.json")

# Terminal / tmux
TMUX_WEB_SESSION = os.environ.get("CARROT_TMUX_WEB_SESSION", "carrot-terminal")
TMUX_CAPTURE_LINES = 160
TMUX_START_DIR = "/data/openpilot"

# Internal services
WEBRTCD_URL = "http://127.0.0.1:5001/stream"

# UI
UNIT_CYCLE = [1, 2, 5, 10, 50, 100]

# Third-party Discord destinations are OFF by default in this fork, like the recovery server
# and web_upload. The dashcam / vision-diag "send log" actions therefore report not-configured
# unless the operator supplies a webhook URL via the CARROT_*_DISCORD_WEBHOOK_URL env vars.
DASHCAM_DEFAULT_DISCORD_WEBHOOK = ""
DASHCAM_DEFAULT_DISCORD_KEY = ""
VISION_DIAG_DEFAULT_DISCORD_WEBHOOK = ""
VISION_DIAG_DEFAULT_DISCORD_KEY = ""

# Kept for the ported git/tool code: this fork keeps its own /data/carrot/state layout, so
# these only matter when the state directory is relocated by CARROT_DATA_DIR.
CARROT_DATA_DIR = os.environ.get("CARROT_DATA_DIR", "/data/carrot")

"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
"""Configuration for the carrot API server."""

import os

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 7000

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

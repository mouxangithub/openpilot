"""Shared imports for Cabana submodules."""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiohttp import web

from ai.services.cabana.replay_util import (
  REPLAY_SNAPSHOT_INTERVAL,
  build_replay_snapshots as _build_replay_snapshots,
  compact_can_batch as _compact_can_batch,
  latest_frames_at_rel as _latest_frames_at_rel,
)

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

try:
  from cereal import messaging
except ImportError:
  messaging = None  # type: ignore

try:
  from opendbc.can.dbc import DBC
  from opendbc.car.values import PLATFORMS
except ImportError:
  DBC = None  # type: ignore
  PLATFORMS = {}  # type: ignore

try:
  from opendbc import DBC_PATH, get_generated_dbcs
except ImportError:
  DBC_PATH = ""  # type: ignore
  def get_generated_dbcs() -> dict[str, str]:  # type: ignore
    return {}

try:
  from openpilot.tools.lib.logreader import LogReader
except ImportError:
  LogReader = None  # type: ignore

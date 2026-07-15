#!/usr/bin/env python3
"""Start op 助手 with scons native modules + venv aiohttp."""
import os
import sys

ROOT = os.environ.get("OPENPILOT_ROOT", "/data/openpilot")
VENV_SITE = "/usr/local/venv/lib/python3.12/site-packages"
os.environ["PYTHONPATH"] = ROOT + ":" + VENV_SITE + (
  (":" + os.environ["PYTHONPATH"]) if os.environ.get("PYTHONPATH") else ""
)
os.chdir(ROOT)
os.execvp("python3.12", ["python3.12", "-m", "ai.aid"])

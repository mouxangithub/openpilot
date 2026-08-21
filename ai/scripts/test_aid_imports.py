#!/usr/bin/env python3
import os
import sys
root = "/data/openpilot"
venv = "/usr/local/venv/lib/python3.12/site-packages"
os.environ["PYTHONPATH"] = root + ":" + venv
sys.path[:0] = [root, venv]
print("python", sys.version)
try:
    from openpilot.common.params import Params
    print("params_ok")
except Exception as e:
    print("params_fail", e)
try:
    import aiohttp
    print("aiohttp_ok", aiohttp.__version__)
except Exception as e:
    print("aiohttp_fail", e)

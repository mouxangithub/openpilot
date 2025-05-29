# tsk/common/env.py
import os
import time


RECOMMENDED_OP_USER = "commaai"
RECOMMENDED_OP_BRANCH = "nightly-dev"
RECOMMENDED_OP_DIR = "/data/tsk-recommended"
ALTERNATE_OP_USER = "sunnypilot"
ALTERNATE_OP_BRANCH = "staging-c3-new"
ALTERNATE_OP_DIR = "/data/tsk-alternate"


def is_agnos():
  return os.path.exists("/AGNOS")


def is_calvins_c3x() -> bool:
  try:
    with open("/persist/comma/dongle_id") as f:
      content = f.read()
      if "2decf199" in content:
        return True

  except:
    pass

  return False


def is_cache_dir_new() -> bool:
  try:
    cache_dir = "/cache/params"
    mod_time = os.path.getmtime(cache_dir)
    age = time.time() - mod_time
    day = 60 * 60 * 24

    return age < day

  except:
    pass

  return False


def is_in_car() -> bool:
  return False

# tsk/lib/env.py
import os
import time
from pathlib import Path

def is_agnos():
  return os.path.exists("/AGNOS")


COMMA_DATA_DIR = "/data" if is_agnos() else f"{os.path.expanduser('~')}/comma_data"

PAYLOAD_PATH = str(Path(__file__).parent / "payload.bin")
DATAFLASH_PAYLOAD_PATH = str(Path(__file__).parent / "payload_dataflash_ff200000_ff208000.bin")

# CAN messages and DataFlash dumps live under /cache so they survive reboot but
# clear on AGNOS update. Off-device they go under ~/comma_data for dry-run testing.
CACHE_DIR = "/cache" if is_agnos() else f"{COMMA_DATA_DIR}/cache"
DATAFLASH_DIR = f"{CACHE_DIR}/tsk/dataflash"
CAN_MESSAGES_DIR = f"{CACHE_DIR}/tsk/can-messages"
CAN_ORACLE_PATH = f"{CAN_MESSAGES_DIR}/can_oracle.ndjson"


def is_calvins_comma() -> bool:
  try:
    with open("/persist/comma/dongle_id") as f:
      content = f.read()
      if "2decf199" in content or "eecdfcc" in content:
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


def setup():
  if not is_calvins_comma():
    return

  params_dir = "/data/params/d"
  files = {
    "GithubUsername": "calvinpark",
    "GithubSshKeys": (
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD30Dz8yY3n1DchzsPbuuWMXMBtyeW2Yh5aOjrjLSvUBjqs9OoPrPfOMAPiaKqE6EfEcjV90He9A6q7OywTy5kTD6JsjjoULJKHiGbDdQlclXE2fO/wTnmxPO9yjdDJqiFrPsSGbT/4R78TVUUkEwD+6DcDGtJd7hHQ/GQCWn78kZ/UsZqcukGjhuwI98gOnIOmX3ui2W6/2NrP3IH7GJWnIvDIHafHYwnRkNU7WQ5zyiUw2GX65dTrXt0pDpX/nYp0qjwORf91DTZCg6fimdUo2WAmhYXnQb66IKESpNVfIVA8L0PRNkSepc3RARX0bPgqYGj6TLy9s87UT11mq/ASuIo9IVYWt6okYvloQcwrX6uxKsGutXouXDraxP648s1ErM6BC3tOOagay19cZdQl53k0CZbkIXODlpM/QaW7MdagH7PVzlGGIuHohDAe3M/ltJjRmRfdj89cCGusBlFB5RuLZpzYskp353NZ1qxhL086Mfyg0bBdDK+CGLJ7bY0=\n"
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILXx7npi7/QYSOu2Z0Bhldtey4L2nxEyZKYQY/BIHdak"
    ),
    "SshEnabled": "1",
    "HasAcceptedTerms": "2",
    "CompletedTrainingVersion": "0.2.0",
  }
  for name, value in files.items():
    with open(f"{params_dir}/{name}", "w") as f:
      f.write(value)

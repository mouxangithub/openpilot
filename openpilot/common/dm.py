import os

from openpilot.common.params import Params


def is_dm_disabled(params: Params | None = None) -> bool:
  if os.getenv("LITE") is not None:
    return True
  p = params if params is not None else Params()
  return p.get_bool("DisableDM")

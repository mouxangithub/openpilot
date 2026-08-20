"""openpilot Params compatibility: libparams_c.so (new) vs params_pyx.so (legacy)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Type, TypeVar

ParamsNativeKind = Literal["libparams_c", "params_pyx"]

# Prefer new sunnypilot layout; fall back to legacy Cython extension.
NATIVE_SO_REL_PATHS: tuple[str, ...] = (
  "openpilot/common/libparams_c.so",
  "common/libparams_c.so",
  "openpilot/common/params_pyx.so",
  "common/params_pyx.so",
)

_LIBPARAMS_C_SO_PATHS = NATIVE_SO_REL_PATHS[:2]
_PARAMS_PYX_SO_PATHS = NATIVE_SO_REL_PATHS[2:]

T = TypeVar("T")


def find_params_native_so(root: Path) -> Path | None:
  for rel in NATIVE_SO_REL_PATHS:
    path = root / rel
    if path.is_file():
      return path
  return None


def detect_params_native_kind(root: Path) -> ParamsNativeKind | None:
  """Infer which native backend the tree's params.py expects."""
  for rel in ("openpilot/common/params.py", "common/params.py"):
    params_py = root / rel
    if not params_py.is_file():
      continue
    text = params_py.read_text(encoding="utf-8", errors="replace")
    if "libparams_c" in text:
      return "libparams_c"
    if "params_pyx" in text:
      return "params_pyx"
  if any((root / rel).is_file() for rel in _LIBPARAMS_C_SO_PATHS):
    return "libparams_c"
  if any((root / rel).is_file() for rel in _PARAMS_PYX_SO_PATHS):
    return "params_pyx"
  return None


def scons_native_targets(kind: ParamsNativeKind | None) -> list[str]:
  if kind == "params_pyx":
    return list(_PARAMS_PYX_SO_PATHS)
  if kind == "libparams_c":
    return list(_LIBPARAMS_C_SO_PATHS)
  return list(NATIVE_SO_REL_PATHS)


def import_openpilot_params() -> tuple[Type[T], Type[BaseException]]:
  """Return (Params, UnknownKeyName) for the installed openpilot tree."""
  from openpilot.common.params import Params

  try:
    from openpilot.common.params import UnknownKeyName
  except ImportError:
    from openpilot.common.params_pyx import UnknownKeyName  # type: ignore[import-not-found]
  return Params, UnknownKeyName


find_params_pyx_so = find_params_native_so  # legacy name

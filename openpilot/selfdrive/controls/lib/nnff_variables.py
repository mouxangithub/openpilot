#!/usr/bin/env python3
"""NNFF model discovery for this fork (StarPilot starpilot_variables subset).

Models live in selfdrive/assets/nnff_models (one JSON per vehicle). Car
substitutes reuse opendbc's torque_data/substitute.toml plus a fork-local
map for fingerprints opendbc does not know (e.g. the Wildlander PHEV is a
RAV4 Prime rebadge).
"""
import tomllib
from functools import cache
from pathlib import Path

BASEDIR = Path(__file__).resolve().parents[3]  # openpilot/
NNFF_MODELS_PATH = BASEDIR / "selfdrive/assets/nnff_models"

_TORQUE_SUBSTITUTE_PATH = BASEDIR.parents[0] / "opendbc_repo" / "opendbc" / "car" / "torque_data" / "substitute.toml"
if not _TORQUE_SUBSTITUTE_PATH.exists():
  # scons-packaged device layout: opendbc sits next to openpilot/ under /data/openpilot
  _TORQUE_SUBSTITUTE_PATH = BASEDIR.parent / "opendbc" / "car" / "torque_data" / "substitute.toml"

# Fork-local substitutes: fingerprints this fork adds on top of opendbc
FORK_SUBSTITUTES = {
  "TOYOTA_WILDLANDER_PHEV": "TOYOTA_RAV4_PRIME",
}


def get_nnff_model_files() -> list[str]:
  if not NNFF_MODELS_PATH.is_dir():
    return []
  return [file.stem for file in NNFF_MODELS_PATH.iterdir() if file.is_file()]


@cache
def get_nnff_substitutes() -> dict[str, str]:
  substitutes = dict(FORK_SUBSTITUTES)
  try:
    with open(_TORQUE_SUBSTITUTE_PATH, "rb") as f:
      data = tomllib.load(f)
    # substitute.toml is a flat map of "CAR" = "OTHER" (plus a legend list)
    for key, value in data.items():
      if isinstance(key, str) and isinstance(value, str):
        substitutes[key] = value
  except (OSError, tomllib.TOMLDecodeError):
    pass
  return substitutes


def nnff_supported(car_fingerprint: str) -> bool:
  from openpilot.selfdrive.controls.lib.neural_network_feedforward import get_nn_model_path
  return get_nn_model_path(car_fingerprint, "") is not None

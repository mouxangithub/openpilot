"""
Copyright (c) 2026-, mouxan.

Query layer over the StarPilot v25 model source map.

``model_source_map_v25.json`` is a verbatim copy of StarPilot's
``scripts/model_source_map_v25.json``: a pure-data reference catalog mapping
89 driving model ids to the git ref they were compiled from, their input
format, and the compiler source id. sunnypilot's model selection and naming
are different and remain untouched; this catalog is read-only metadata for
tools that need to know where a StarPilot-era artifact came from.

Structure: ``{model_id: {"ref": <git sha>, "input_format": "split"|"...",
                          "source_id": <compiler source key>}}``
"""
import json
import os

CATALOG_VERSION = "v25"
CATALOG_FILENAME = f"model_source_map_{CATALOG_VERSION}.json"
CATALOG_PATH = os.path.join(os.path.dirname(__file__), CATALOG_FILENAME)

_cache: dict | None = None


def load_catalog(force_reload: bool = False) -> dict:
  """Load (and memoize) the v25 source map. Returns {} if the file is missing or invalid."""
  global _cache
  if _cache is not None and not force_reload:
    return _cache
  try:
    with open(CATALOG_PATH, encoding="utf-8") as f:
      catalog = json.load(f)
    _cache = catalog if isinstance(catalog, dict) else {}
  except (OSError, ValueError):
    _cache = {}
  return _cache


def list_model_ids() -> list[str]:
  """All model ids present in the v25 catalog."""
  return list(load_catalog().keys())


def has_v25_artifact(model_id: str) -> bool:
  return model_id in load_catalog()


def get_artifact_info(model_id: str) -> dict | None:
  """The full catalog entry for a model id, or None."""
  return load_catalog().get(model_id)


def get_ref(model_id: str) -> str | None:
  entry = get_artifact_info(model_id)
  return entry.get("ref") if entry else None


def get_input_format(model_id: str) -> str | None:
  entry = get_artifact_info(model_id)
  return entry.get("input_format") if entry else None


def get_source_id(model_id: str) -> str | None:
  entry = get_artifact_info(model_id)
  return entry.get("source_id") if entry else None


def find_by_source_id(source_id: str) -> list[str]:
  """Model ids compiled from a given compiler source key."""
  return sorted(model_id for model_id, entry in load_catalog().items() if entry.get("source_id") == source_id)

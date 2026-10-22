# Model Selector Version Compatibility

This document explains the version compatibility mechanism used by the Model Selector system, and the rationale behind certain version constraints and JSON file management strategies.

## Overview

The Model Selector is responsible for selecting and validating model bundles based on their metadata and version constraints. Each model bundle is distributed via a JSON file and includes a `minimumSelectorVersion` field indicating the minimum selector version required to load it.

To ensure robust compatibility and prevent mismatches between model expectations and selector capabilities, the selector enforces two version boundaries:

* **`REQUIRED_MIN_SELECTOR_VERSION`**: the oldest selector version we support.
* **`CURRENT_SELECTOR_VERSION`**: the current version of the selector logic.

## Version Compatibility Check

A model bundle is considered compatible if:

```python
REQUIRED_MIN_SELECTOR_VERSION <= bundle["minimumSelectorVersion"] <= CURRENT_SELECTOR_VERSION
```

This ensures:

* **Old bundles are rejected** if they rely on deprecated selector behavior.
* **Future bundles are ignored** if they expect logic that the current selector doesn't yet implement.

## Handling Breaking Changes

When a deep change in selector behavior requires *all* models to be recompiled (e.g., due to a major architectural update), we:

1. **Create a new JSON file** (e.g., from `models_v4.json` to `models_v5.json`).
2. **Assign updated `minimumSelectorVersion` values** in the new bundles.

This allows older selector versions to continue using the previous JSON file, while newer versions point to the new one, preventing cross-contamination.

## Why `REQUIRED_MIN_SELECTOR_VERSION` Still Matters

Despite using new JSON files to isolate breaking changes, `REQUIRED_MIN_SELECTOR_VERSION` plays a critical role:

### 1. **Cached Bundle Validation**

Model bundles are cached locally (e.g., in-memory or on disk). A user might have previously loaded a now-invalid bundle from an older JSON file.

`REQUIRED_MIN_SELECTOR_VERSION` prevents the selector from reloading or trusting that stale cached bundle, even if the original JSON is gone.

### 2. **Explicit Deprecation Boundary**

By raising `REQUIRED_MIN_SELECTOR_VERSION`, we declare older bundles officially unsupported, even if they technically still exist in a legacy JSON file.

### 3. **Avoiding Race Conditions**

Some clients may have intermittent access to updated JSONs. The runtime check ensures version compatibility is enforced independently of external file state.

## Summary

| Component                       | Purpose                                                               |
| ------------------------------- | --------------------------------------------------------------------- |
| `minimumSelectorVersion`        | Declares the minimum selector version required to load a model bundle |
| `REQUIRED_MIN_SELECTOR_VERSION` | Prevents loading bundles that are too old (e.g., from stale cache)    |
| `CURRENT_SELECTOR_VERSION`      | Prevents loading bundles that are too new or forward-incompatible     |
| JSON file renaming              | Isolates bundles by selector generation to handle full recompiles     |

This layered strategy ensures safe evolution of the model selection system while maintaining backward compatibility and runtime protection against stale or incompatible bundles.

## StarPilot Porting Notes (2026-10)

Infrastructure ported from the StarPilot repo (starpilot/assets/download_functions.py, scripts/model_source_map_v25.json), fused with sunnypilot's existing model management:

- **`chunked_download.py`** — standalone reusable module for chunked artifact downloads. Wire protocol matches `openpilot.common.file_chunker`: `<artifact>.chunkmanifest` holds the chunk count, bodies live in `<artifact>.chunkNNofNN`, and the whole artifact is sha256-verified during transfer. Unlike the StarPilot original, download sources are parameterized: `try_download_chunked(destination, base_urls, ...)` takes an ordered list of base URLs (e.g. HuggingFace first, GitHub fallback — the caller decides, nothing is hardcoded) and probes each for a `.chunkmanifest`. Progress and cancellation are plain callbacks. Return values: `None` = no manifest anywhere (caller falls back to the plain single-file download), `True` = verified and laid out in `file_chunker` format (readable by `open_file_chunked` / `helpers._compute_hash`), `False` = transfer failed or cancelled. `candidate_base_urls(params, primary, fallbacks)` helps build the URL list with the sp HF-mirror Params applied.
- **`model_source_map_v25.json` / `model_catalog.py`** — a verbatim copy of StarPilot's v25 model source map (89 model ids → `{ref, input_format, source_id}`), used read-only through `model_catalog.py` (`list_model_ids`, `get_artifact_info`, `has_v25_artifact`, `find_by_source_id`). Pure reference metadata; it does not participate in sp's model selection or naming.
- **Fetcher fusion point** — `manager.py::_process_artifact` (the actual HTTP download site). For artifacts the catalog lists *without* per-chunk hashes, `_try_chunked_download` first probes the remote for a `.chunkmanifest`; if none exists the original single-file `_download_file` path runs byte-for-byte as before. Artifacts with catalog-declared chunks keep using the existing `_download_chunked` per-chunk-sha256 path untouched.
- **Not ported** — StarPilot's Model Randomizer and Model Laboratory: sp has no corresponding model-selection layer for them, and sp's model keys/naming differ from StarPilot's (the existing model patch system is intentionally left alone).

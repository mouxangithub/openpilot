"""
Copyright (c) 2026-, mouxan.

Storage usage helpers for the on-device Storage panel.

Pure functions over paths so the math is testable on a PC without the
hardware stack: each category is a label, the directory it occupies and the
human-readable size on disk. Deletion lives in the panel because it also
clears the params a downloader keys off (see settings/storage.py).
"""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass


MB = 1024 ** 2
GB = 1024 ** 3


@dataclass(frozen=True)
class DiskUsage:
  total: int
  used: int
  free: int

  @property
  def used_fraction(self) -> float:
    return (self.used / self.total) if self.total else 0.0


def disk_usage(path: str) -> DiskUsage | None:
  """Total/used/free bytes of the filesystem backing `path`, or None when it
  cannot be stat-ed (a PC without the device mount)."""
  try:
    st = os.statvfs(path)
  except (OSError, AttributeError):
    return None
  total = st.f_blocks * st.f_frsize
  free = st.f_bavail * st.f_frsize
  return DiskUsage(total=total, used=total - st.f_bfree * st.f_frsize, free=free)


def directory_size(path: str) -> int:
  """Recursive bytes under a directory; 0 when it is absent. Symlinks are not
  followed, so a linked path never counts its target twice."""
  total = 0
  if not os.path.isdir(path):
    return 0
  stack = [path]
  while stack:
    current = stack.pop()
    try:
      with os.scandir(current) as entries:
        for entry in entries:
          if entry.is_symlink():
            continue
          if entry.is_file(follow_symlinks=False):
            with contextlib.suppress(OSError):
              total += entry.stat(follow_symlinks=False).st_size
          elif entry.is_dir(follow_symlinks=False):
            stack.append(entry.path)
    except OSError:
      pass
  return total


def format_size(num_bytes: int) -> str:
  """'12.34 MB' / '1.20 GB', matching the rest of the settings UI."""
  if num_bytes >= GB:
    return f"{num_bytes / GB:.2f} GB"
  return f"{num_bytes / MB:.2f} MB"


def model_root_size(model_root: str) -> int:
  """Bytes the driving-model cache occupies, recursively.

  Both the web UI and the big UI must quote the same number: the small
  (qcom) and big (chestnut) models share one flat model directory, so the
  directory walk is the source of truth, not a catalog entry that may be
  stale. This deliberately counts chunks (the .chunkNofM layout) too, so a
  half-finished download shows the space it already took."""
  return directory_size(model_root)


def model_file_names(bundle) -> set[str]:
  """File names a bundle places in the model root: every model's artifact and
  metadata. Artifacts hang off bundle.models[] - ModelBundle itself has no
  artifacts field (custom.capnp), which once made the size rows read 0."""
  names: set[str] = set()
  for model in getattr(bundle, "models", []) or []:
    for artifact in (getattr(model, "artifact", None), getattr(model, "metadata", None)):
      name = getattr(artifact, "fileName", "") or ""
      if name:
        names.add(name)
  return names


def cached_bundle_sizes(model_root: str, bundles_by_source: dict[str, list]) -> dict[str, int]:
  """Per-source on-disk bytes of the bundles a source's catalog lists.

  The filesystem cannot tell which file feeds qcom versus chestnut (they
  share the directory and differ only by catalog), so attribution follows
  each source's cached bundle list. An artifact is summed from the chunks
  that are actually on disk via the shared size ledger; a name listed by
  both sources is attributed to both (it really does serve both), while the
  row that matters - the directory total in model_root_size - never double
  counts. Returns {source: bytes} for every source passed in, 0 when a
  source has nothing local yet.
  """
  try:
    from openpilot.sunnypilot.models.model_sizes import artifact_size
  except Exception:
    # Keep the storage layer importable on a PC without the model stack:
    # fall back to a plain complete-file stat when the ledger is absent.
    def artifact_size(path, declared=None):  # type: ignore[no-redef]
      try:
        return {"downloadedBytes": os.path.getsize(path) if os.path.isfile(path) else None}
      except OSError:
        return {"downloadedBytes": None}

  sizes = dict.fromkeys(bundles_by_source, 0)
  for source, bundles in bundles_by_source.items():
    for bundle in bundles or []:
      for model in getattr(bundle, "models", []) or []:
        # artifacts hang off each model (Model.artifact / Model.metadata in
        # custom.capnp); ModelBundle itself has no artifacts field
        for artifact in (getattr(model, "artifact", None), getattr(model, "metadata", None)):
          file_name = getattr(artifact, "fileName", "") or ""
          if not file_name:
            continue
          declared = getattr(artifact, "fileSizeBytes", None)
          on_disk = artifact_size(os.path.join(model_root, file_name), declared).get("downloadedBytes")
          if on_disk:
            sizes[source] += int(on_disk)
  return sizes

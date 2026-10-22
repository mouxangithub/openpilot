"""
Copyright (c) 2026-, mouxan.

Chunked model artifact download with sha256 verification, ported from StarPilot's
``starpilot/assets/download_functions.py`` (download_chunked_file) and fused with
sunnypilot's ``openpilot.common.file_chunker`` on-disk protocol.

Wire protocol (identical to StarPilot / file_chunker):
- ``<artifact>.chunkmanifest``        plain-text chunk count, e.g. ``4``
- ``<artifact>.chunk01of04`` ...      the chunk bodies, 1-based zero-padded NNofNN

Differences from the StarPilot original:
- No hardcoded sources. The caller supplies an ordered list of base URLs
  (``base_urls``); the first candidate that serves a valid ``.chunkmanifest``
  wins, so "HF first, GitHub fallback" is expressed by the caller's ordering.
- Progress and cancellation are plain callbacks instead of StarPilot's
  params_memory keys, so this module stays decoupled from the UI.
- On-disk layout uses openpilot.common.file_chunker, which is the same naming
  scheme sunnypilot's model manager already reads (open_file_chunked).
"""
import hashlib
import tempfile
import urllib.parse

from pathlib import Path

# A Git LFS pointer file starts with this exact line. It stands in for the
# real artifact and must never be published as one.
LFS_POINTER = b'version https://git-lfs.github.com/spec/v1'

import requests

from openpilot.common.file_chunker import get_chunk_name, get_manifest_path

# (connect, read) seconds. read is per-request inactivity, not a total cap
DOWNLOAD_TIMEOUT = (10, 60)
READ_CHUNK_SIZE = 1024 * 1024
MAX_CHUNKS = 100

_MANIFEST_SUFFIX = ".chunkmanifest"


class ChunkedDownloadError(Exception):
  """The chunked transfer ran but produced an unverifiable artifact."""


def normalize_download_url(url: str) -> str:
  """Force Dropbox share links to direct download; other hosts pass through."""
  parsed = urllib.parse.urlsplit(str(url or "").strip())
  if parsed.netloc.lower() not in {"dropbox.com", "www.dropbox.com"}:
    return url
  query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
  query = [(key, value) for key, value in query if key != "dl"]
  query.append(("dl", "1"))
  return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def sha256_file(path) -> str:
  """Streaming sha256 of a local file, lowercase hex."""
  digest = hashlib.sha256()
  with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(READ_CHUNK_SIZE), b""):
      digest.update(chunk)
  return digest.hexdigest()


def candidate_base_urls(params, primary: str, fallbacks=()) -> list[str]:
  """Ordered download candidates: the primary URL (usually huggingface.co,
  rewritten through the sunnypilot mirror Params) first, then any fallbacks
  (e.g. GitHub) in the order the caller wants them tried."""
  fallbacks = list(fallbacks)
  if params is not None:
    try:
      from openpilot.sunnypilot.models.mirror import apply_hf_mirror, get_hf_mirror_base
      primary = apply_hf_mirror(primary, get_hf_mirror_base(params))
    except Exception:
      pass  # mirror config is best-effort; the raw URL still works
  return [primary] + [url for url in fallbacks if url and url != primary]


def fetch_chunk_manifest(base_url: str, timeout=DOWNLOAD_TIMEOUT) -> int | None:
  """Fetch and parse ``<url>.chunkmanifest``; None when absent or malformed."""
  url = normalize_download_url(base_url) + _MANIFEST_SUFFIX
  try:
    response = requests.get(url, timeout=timeout)
    if response.status_code == 404:
      return None
    response.raise_for_status()
    chunk_count = int(response.text.strip())
  except (requests.RequestException, ValueError):
    return None
  if chunk_count <= 0 or chunk_count > MAX_CHUNKS:
    return None
  return chunk_count


def delete_chunked_artifact(destination) -> None:
  """Remove a logical artifact plus its manifest and every native chunk."""
  destination = Path(destination)
  destination.unlink(missing_ok=True)
  Path(get_manifest_path(destination)).unlink(missing_ok=True)
  for chunk_path in destination.parent.glob(f"{destination.name}.chunk*of*"):
    chunk_path.unlink(missing_ok=True)


def try_download_chunked(destination, base_urls, expected_size=None, expected_sha256=None,
                         expected_chunk_count=None, progress_cb=None, cancel_cb=None) -> bool | None:
  """Download a chunked artifact without reassembling it on disk.

  Tries each base URL in order. Returns:
  - None  when no candidate serves a .chunkmanifest (caller should fall back
    to the plain single-file download path)
  - True  when the artifact was downloaded into file_chunker layout and verified
  - False on a failed/cancelled transfer (partial state is cleaned up)

  progress_cb(percent: float) fires during transfer and once with 100 on verify;
  cancel_cb() returning True aborts without raising.
  """
  for base_url in base_urls:
    chunk_count = fetch_chunk_manifest(base_url)
    if chunk_count is not None:
      return _download_from_source(destination, base_url, chunk_count, expected_size=expected_size,
                                   expected_sha256=expected_sha256, expected_chunk_count=expected_chunk_count,
                                   progress_cb=progress_cb, cancel_cb=cancel_cb)
  return None


def _download_from_source(destination, base_url, chunk_count, expected_size=None, expected_sha256=None,
                          expected_chunk_count=None, progress_cb=None, cancel_cb=None) -> bool:
  destination = Path(destination)
  expected_size = int(expected_size or 0)
  expected_sha256 = str(expected_sha256 or "").strip().lower()
  expected_chunk_count = int(expected_chunk_count or 0)
  if expected_chunk_count and chunk_count != expected_chunk_count:
    raise ChunkedDownloadError(f"Chunk count mismatch for {destination.name}: {chunk_count} != {expected_chunk_count}")

  destination.parent.mkdir(parents=True, exist_ok=True)

  def report(percent: float) -> None:
    if progress_cb:
      progress_cb(percent)

  def cancelled() -> bool:
    return bool(cancel_cb and cancel_cb())

  try:
    chunk_urls = [normalize_download_url(base_url) + f".chunk{i + 1:02d}of{chunk_count:02d}" for i in range(chunk_count)]
    chunk_sizes = [_remote_file_size(url) for url in chunk_urls]
    if any(size <= 0 for size in chunk_sizes):
      return False
    remote_size = sum(chunk_sizes)
    if expected_size and remote_size != expected_size:
      raise ChunkedDownloadError(f"Artifact size mismatch for {destination.name}: {remote_size} != {expected_size}")

    temporary_paths: list[Path] = []
    downloaded_size = 0
    digest = hashlib.sha256()
    try:
      for chunk_url, chunk_size in zip(chunk_urls, chunk_sizes, strict=True):
        if cancelled():
          return False
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output_file:
          temporary_path = Path(output_file.name)
          temporary_paths.append(temporary_path)
          actual_chunk_size = 0
          with requests.get(chunk_url, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
            response.raise_for_status()
            for data in response.iter_content(chunk_size=READ_CHUNK_SIZE):
              if cancelled():
                return False
              if not data:
                continue
              output_file.write(data)
              digest.update(data)
              actual_chunk_size += len(data)
              downloaded_size += len(data)
              report(min(99.0, downloaded_size / remote_size * 100))
          if actual_chunk_size != chunk_size:
            return False

      report(100)
      if expected_size and downloaded_size != expected_size:
        raise ChunkedDownloadError(f"Downloaded size mismatch for {destination.name}: {downloaded_size} != {expected_size}")
      if expected_sha256 and digest.hexdigest() != expected_sha256:
        raise ChunkedDownloadError(f"SHA-256 mismatch for chunked {destination.name}")
      if _is_lfs_pointer_file(temporary_paths):
        # The server handed back a Git LFS pointer instead of the artifact.
        # Publishing it would leave a model that looks installed but is not.
        raise ChunkedDownloadError(f"Artifact {destination.name} is a Git LFS pointer, not the model")

      # promote the verified temp files into file_chunker layout
      delete_chunked_artifact(destination)
      for index, temporary_path in enumerate(temporary_paths):
        temporary_path.replace(Path(get_chunk_name(destination, index, chunk_count)))
      temporary_paths.clear()
      Path(get_manifest_path(destination)).write_text(str(chunk_count))
      return True
    finally:
      for temporary_path in temporary_paths:
        temporary_path.unlink(missing_ok=True)
  except ChunkedDownloadError:
    delete_chunked_artifact(destination)
    raise
  except (requests.RequestException, OSError):
    return False


def _is_lfs_pointer_file(paths) -> bool:
  """Whether any of the downloaded files is a Git LFS pointer.

  A pointer is a ~130 byte text file. When the expected size is not known it
  would pass the size check and only fail on the checksum, which reads as a
  corrupt download rather than as "the server served the wrong thing".
  """
  for path in paths:
    try:
      with open(path, 'rb') as f:
        if f.read(len(LFS_POINTER)) == LFS_POINTER:
          return True
    except OSError:
      continue
  return False


def _remote_file_size(url: str) -> int:
  try:
    response = requests.head(url, headers={"Accept-Encoding": "identity"}, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return int(response.headers.get("Content-Length", 0))
  except (requests.RequestException, ValueError):
    return 0

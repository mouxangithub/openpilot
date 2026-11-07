"""Local size ledger for model artifacts, without touching the network.

The model picker wants to say "downloaded", "42% on disk" or "not here"
about each bundle. Answering that from the manager's download progress
only works while the manager is downloading; an interrupted fetch leaves
chunks on disk that no message describes, and a bundle picked long ago
has no progress at all. This ledger derives the answer from the local
filesystem instead: complete file, chunk set, or nothing.

No HEAD requests, no hashing, no mutation -- stat() only, with a small
time-bounded cache so a picker that re-renders while the user scrolls
does not rescan the model directory per frame. The chunk naming and the
manifest format are the ones ``common/file_chunker`` writes; that module
is deliberately not imported so this file stays importable on a PC that
has neither numpy nor cereal.
"""
import re
import threading
import time
from pathlib import Path

# Refuse absurd declared sizes: a corrupted catalog entry must not be
# reported as a real download target.
MAX_DECLARED_BYTES = 1 << 50

CACHE_TTL_S = 2.0
CACHE_MAX_ENTRIES = 1000

# {name}.chunk01ofNN -- the same shape file_chunker.get_chunk_name writes.
_CHUNK_RE_SUFFIX = r"\.chunk\d+of\d+"


def positive_size(value) -> int | None:
  return value if type(value) is int and 0 < value <= MAX_DECLARED_BYTES else None


def chunk_file_name(name: str, idx: int, num_chunks: int) -> str:
  """Must stay byte-identical to common/file_chunker.get_chunk_name."""
  return f"{name}.chunk{idx + 1:02d}of{num_chunks:02d}"


def artifact_size(path, declared=None) -> dict:
  """How much of the artifact at ``path`` is on disk.

  ``declared`` is the catalog's byte count, when it has one. The answer
  always carries fileSizeBytes / downloadedBytes / sizeSource /
  sizeStatus; a None size with an "unknown" status is a valid answer,
  not a failure.
  """
  path = Path(path)
  declared = positive_size(declared)
  result = {'fileSizeBytes': None, 'declaredSizeBytes': declared, 'downloadedBytes': None,
            'chunksExpected': None, 'chunksPresent': None,
            'sizeSource': 'metadata' if declared else 'unknown',
            'sizeStatus': 'declared' if declared else 'unknown'}
  try:
    if path.is_file():
      size = path.stat().st_size
      result.update(fileSizeBytes=size if size > 0 else None, downloadedBytes=size,
                    sizeSource='installed', sizeStatus='complete' if size > 0 else 'partial')
    else:
      # Chunked layout: a manifest naming the chunk count, plus however many
      # chunk files made it down before the fetch stopped. A complete chunk
      # set reads as complete even before the join: the bytes are all here,
      # and the hash check at join time is what actually gates usage.
      manifest = Path(str(path) + '.chunkmanifest')
      chunks = [p for p in path.parent.glob(path.name + '.chunk*')
                if re.fullmatch(re.escape(path.name) + _CHUNK_RE_SUFFIX, p.name) and p.is_file()]
      if not manifest.is_file() and not chunks:
        return result
      count = None
      if manifest.is_file():
        try:
          text = manifest.read_text().strip()
          count = int(text) if text.isdecimal() and len(text) <= 5 else None
        except (ValueError, UnicodeError):
          pass
      expected = [Path(f'{path}.chunk{i + 1:02d}of{count:02d}') for i in range(count)] if count and count <= 10000 else []
      complete = bool(expected) and set(chunks) == set(expected)
      downloaded = sum(p.stat().st_size for p in chunks)
      result.update(downloadedBytes=downloaded, fileSizeBytes=downloaded if complete and downloaded > 0 else None,
                    chunksExpected=count, chunksPresent=len(chunks),
                    sizeSource='installed' if complete else 'partial',
                    sizeStatus='complete' if complete and downloaded > 0 else 'partial')
    if result['fileSizeBytes'] is not None and declared and declared != result['fileSizeBytes']:
      result['sizeStatus'] = 'mismatch'
  except OSError:
    result.update(fileSizeBytes=None, downloadedBytes=None, sizeSource='unknown', sizeStatus='unknown')
  return result


class ModelSizes:
  """Bounded cache for local size reads, so a re-rendering picker is cheap."""

  def __init__(self):
    self.lock = threading.Lock()
    self.sizes = {}

  def size(self, path, declared) -> dict:
    key = (str(path), repr(declared))
    with self.lock:
      cached = self.sizes.get(key)
      if cached is None or time.monotonic() >= cached[0]:
        cached = (time.monotonic() + CACHE_TTL_S, artifact_size(path, declared))
        if len(self.sizes) > CACHE_MAX_ENTRIES:
          self.sizes.clear()
        self.sizes[key] = cached
      return dict(cached[1])


def artifact_local_name(model) -> str | None:
  """The local file name a bundle model's artifact lands as, or None.

  A chunked artifact lands as its file name once joined, and as chunk
  files before that; both are described by the file name, so one answer
  serves both questions.
  """
  artifact = getattr(model, 'artifact', None)
  if artifact is None:
    return None
  name = getattr(artifact, 'fileName', None)
  return name if name else None


def bundle_local_status(bundle, model_root, sizes: ModelSizes | None = None) -> dict[str, dict]:
  """Per-file local size records for a bundle, keyed by file name.

  ``bundle`` only needs the duck-typed shape helpers reads: models with
  an artifact that carries a file name. Sharing the walk with
  helpers._bundle_artifacts is deliberate: the two answer different
  questions about the same files (hashes to verify versus bytes on
  disk), and they must never disagree about what those files are.

  There is no declared size in sp's Artifact schema, so a record starts
  from the local bytes alone; ``artifact_size`` still accepts one for
  the day the catalog carries it.
  """
  sizes = sizes or _SIZES
  status: dict[str, dict] = {}
  for model in getattr(bundle, 'models', []) or []:
    name = artifact_local_name(model)
    if name is None or name in status:
      continue
    status[name] = sizes.size(Path(model_root) / name, None)
  return status


def bundle_download_fraction(bundle, model_root, sizes: ModelSizes | None = None) -> float | None:
  """The fraction of a bundle that is on disk, or None when nothing is
  known. Byte-based when declared sizes exist, else chunk-count based
  (sp's catalog carries no sizes, and its chunks are all the same fixed
  size, so counting chunks is an honest approximation). 1.0 is complete."""
  statuses = bundle_local_status(bundle, model_root, sizes)
  if not statuses:
    return None
  known = 0
  have = 0
  expected = 0
  present = 0
  countable = True
  for record in statuses.values():
    if record['declaredSizeBytes']:
      known += record['declaredSizeBytes']
    elif record['fileSizeBytes']:
      known += record['fileSizeBytes']
    have += record['downloadedBytes'] or 0
    if record['chunksExpected'] is None:
      countable = False
    else:
      expected += record['chunksExpected']
      present += min(record['chunksPresent'] or 0, record['chunksExpected'])
  if known > 0:
    return max(0.0, min(1.0, have / known))
  if countable and expected > 0:
    return max(0.0, min(1.0, present / expected))
  return None


_SIZES = ModelSizes()

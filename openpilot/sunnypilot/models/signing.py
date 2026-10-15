"""
Copyright (c) 2026-, mouxan.

Model catalog signature verification (ed25519).

The model catalogs (driving_models*.json on gh-pages) are fetched over plain
HTTPS from a third-party host. Chunk integrity is already checked against the
per-chunk sha256 the catalog itself carries, but that trusts the catalog — an
attacker who can serve a forged catalog can serve a forged model that passes
every hash check. A signed catalog closes that: the publisher signs the exact
catalog bytes, and devices refuse a catalog that does not verify against a
built-in trust root.

Trust model:
- `signing/` next to this file holds trusted ed25519 public keys (PEM). Every
  key in there accepts a catalog.
- No trusted keys installed → verification is advisory: a missing or bad
  signature only logs. This keeps third-party catalogs (the upstream
  sunnypilot-models gh-pages, unsigned) working while sp-published catalogs
  can be locked down by shipping the public key.
- With at least one trusted key installed → verification is mandatory: a
  catalog with no signature, or one that fails, is rejected.
"""
import base64
import hashlib
import logging
from pathlib import Path



logging.getLogger(__name__).setLevel(logging.INFO)
cloudlog = logging.getLogger(__name__)

SIGNING_DIR = Path(__file__).resolve().parent / 'signing'


def _trusted_keys() -> list[bytes]:
  """Every public key PEM shipped in the trust root, empty when none."""
  if not SIGNING_DIR.is_dir():
    return []
  return [p.read_bytes() for p in sorted(SIGNING_DIR.glob('*.pem'))]


def has_trusted_keys() -> bool:
  return len(_trusted_keys()) > 0


def _verify_with_key(catalog_bytes: bytes, signature_b64: str, public_pem: bytes) -> bool:
  try:
    from Crypto.PublicKey import ECC
    from Crypto.Signature import eddsa
    key = ECC.import_key(public_pem)
    payload_hash = hashlib.sha256(catalog_bytes).digest()
    eddsa.new(key, 'rfc8032').verify(payload_hash, base64.b64decode(signature_b64))
    return True
  except Exception:
    return False


def verify_catalog(catalog_bytes: bytes, signature_b64: str | None) -> tuple[bool, str]:
  """Verify a catalog's ed25519 signature against the trust root.

  Returns (accepted, reason). Reasons are only logged by the caller.
  """
  keys = _trusted_keys()
  if not keys:
    if signature_b64:
      # no trust root shipped: record that a signature exists but cannot be checked
      return True, 'unsigned-device: signature present but no trusted key installed'
    return True, 'no trusted keys and no signature'

  if not signature_b64:
    return False, 'catalog is unsigned but a trust root is installed'

  if not any(_verify_with_key(catalog_bytes, signature_b64, key) for key in keys):
    return False, 'catalog signature failed against every trusted key'
  return True, 'catalog signature verified'


def fetch_catalog_signature(model_url: str, timeout: float = 10.0) -> str | None:
  """Best-effort fetch of the catalog's sidecar signature (model_url + '.sig')."""
  import requests
  try:
    response = requests.get(model_url + '.sig', timeout=timeout)
    if response.status_code == 200:
      signature = response.text.strip()
      # the signature covers the exact bytes served for the catalog itself
      return signature or None
    return None
  except Exception:
    return None

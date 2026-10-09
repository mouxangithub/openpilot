"""Sign a model catalog JSON with the release ed25519 key.

  python3 sign_catalog.py --catalog driving_models_v22.json --key model-signing-private.pem

Writes driving_models_v22.json.sig (base64 ed25519 over the exact catalog
bytes) next to the catalog. Upload both to the same directory; devices with
the matching public key in openpilot/sunnypilot/models/signing/ verify the
catalog before accepting it.
"""
import argparse
import base64
import hashlib
from pathlib import Path

from Crypto.PublicKey import ECC
from Crypto.Signature import eddsa


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--catalog', type=Path, required=True)
  parser.add_argument('--key', type=Path, required=True)
  args = parser.parse_args()

  catalog_bytes = args.catalog.read_bytes()
  payload_hash = hashlib.sha256(catalog_bytes).digest()
  key = ECC.import_key(args.key.read_text())
  signature = base64.b64encode(eddsa.new(key, 'rfc8032').sign(payload_hash)).decode()

  sig_path = args.catalog.with_suffix(args.catalog.suffix + '.sig')
  sig_path.write_text(signature + '\n')
  print(f"sha256(catalog) = {payload_hash.hex()}")
  print(f"signature -> {sig_path}")


if __name__ == '__main__':
  main()

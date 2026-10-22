# Model catalog signing

The device refuses a tampered model catalog when a trust root is installed.
Without a trust root everything keeps working as before (unsigned third-party
catalogs like the upstream sunnypilot-models gh-pages stay usable).

## One-time setup

```bash
python3 generate_key.py --out-dir ./keys
# model-signing-private.pem stays with the release pipeline, offline
cp keys/model-signing-public.pem openpilot/sunnypilot/models/signing/
git add openpilot/sunnypilot/models/signing/ && git commit
```

Shipping the public key turns verification **mandatory**: catalogs without a
signature, or with a bad one, are rejected by the model manager.

## Signing a catalog release

```bash
python3 sign_catalog.py --catalog driving_models_v22.json --key keys/model-signing-private.pem
# upload both driving_models_v22.json and driving_models_v22.json.sig
```

The signature covers the exact catalog bytes; the sidecar file is `<catalog>.sig`
(base64 ed25519 over sha256 of the bytes).

## Verification on the device

`openpilot/sunnypilot/models/signing.py` runs on every catalog fetch:
- trust root installed + signature verifies → catalog accepted
- trust root installed + signature missing/invalid → catalog **rejected** (HTTPError, logged)
- no trust root → advisory only (logged, catalog accepted)

Chunk-level sha256 verification of downloaded artifacts was already in place
(models/manager.py); the signature closes the remaining gap: the catalog itself.

Dependencies: pycryptodome (already in the device venv).

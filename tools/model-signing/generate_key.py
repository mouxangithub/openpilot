"""Generate an ed25519 keypair for model catalog signing.

  python3 generate_key.py --out-dir /path/to/keys

Produces:
  model-signing-private.pem  KEEP OFFLINE, never commit
  model-signing-public.pem   ship in openpilot/sunnypilot/models/signing/
"""
import argparse

from Crypto.PublicKey import ECC


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--out-dir', type=str, required=True)
  args = parser.parse_args()

  key = ECC.generate(curve='Ed25519')
  private_pem = key.export_key(format='PEM')
  public_pem = key.public_key().export_key(format='PEM')

  import pathlib
  out = pathlib.Path(args.out_dir)
  out.mkdir(parents=True, exist_ok=True)
  (out / 'model-signing-private.pem').write_text(private_pem)
  (out / 'model-signing-public.pem').write_text(public_pem)
  print(f"private: {out / 'model-signing-private.pem'} (keep offline)")
  print(f"public:  {out / 'model-signing-public.pem'} (ship in openpilot/sunnypilot/models/signing/)")


if __name__ == '__main__':
  main()

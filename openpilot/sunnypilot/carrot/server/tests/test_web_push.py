#!/usr/bin/env python3
import base64
import json
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from openpilot.sunnypilot.carrot.server.services.web_push import (
  build_vapid_authorization,
  encrypt_payload,
  ensure_vapid_keys,
  generate_vapid_keys,
)


def _b64url(data: bytes) -> bytes:
  return base64.urlsafe_b64encode(data).rstrip(b"=")


class TestWebPush(unittest.TestCase):
  def test_generated_keys_are_loadable(self):
    keys = generate_vapid_keys()
    private_key = serialization.load_der_private_key(
      base64.urlsafe_b64decode(keys["private_key"] + "=" * (-len(keys["private_key"]) % 4)), password=None)
    self.assertEqual(private_key.curve.name, "secp256r1")
    self.assertEqual(len(base64.urlsafe_b64decode(keys["public_key"] + "=" * (-len(keys["public_key"]) % 4))), 65)

  def test_encrypt_payload_round_trips_with_client_private_key(self):
    # Simulate the browser side: the client keypair whose public half was
    # subscribed; the server ciphertext must decrypt under the shared secret.
    client_private = ec.generate_private_key(ec.SECP256R1())
    client_public = client_private.public_key().public_bytes(
      serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    p256dh = _b64url(client_public).decode()
    auth_secret = _b64url(b"\x11" * 16).decode()

    payload = b'{"title":"carrot","body":"hello"}'
    body = encrypt_payload(payload, p256dh, auth_secret)

    # aes128gcm header: salt(16) + rs(4) + idlen(1) + server ephemeral point(65)
    self.assertEqual(body[16:20], (4096).to_bytes(4, "big"))
    self.assertEqual(body[20], 65)
    server_public = body[21:86]

    shared = client_private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(
      ec.SECP256R1(), server_public))
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    prk = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"\x11" * 16,
               info=b"WebPush: info\x00" + client_public + server_public).derive(shared)
    salt = body[:16]
    cek = HKDF(algorithm=hashes.SHA256(), length=16, salt=salt,
               info=b"Content-Encoding: aes128gcm\x00").derive(prk)
    nonce = HKDF(algorithm=hashes.SHA256(), length=12, salt=salt,
                 info=b"Content-Encoding: nonce\x00").derive(prk)

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    decrypted = AESGCM(cek).decrypt(nonce, body[86:], None)
    self.assertTrue(decrypted.endswith(b"\x02"))
    self.assertEqual(decrypted[:-1], payload)

  def test_encrypt_rejects_oversized_payload(self):
    client_public = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
      serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    with self.assertRaises(ValueError):
      encrypt_payload(b"x" * 5000, _b64url(client_public).decode(), _b64url(b"0" * 16).decode())

  def test_vapid_authorization_shape(self):
    keys = generate_vapid_keys()
    auth = build_vapid_authorization("https://fcm.googleapis.com/fcm/send/abc", keys)
    self.assertTrue(auth.startswith("vapid t="))
    self.assertIn(f"k={keys['public_key']}", auth)
    token = auth.split("t=", 1)[1].split(",", 1)[0]
    header, claims, signature = token.split(".")
    import base64
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(header)))["alg"], "ES256")
    self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(claims)))["aud"], "https://fcm.googleapis.com")
    # Signature must verify against the published public key.
    from cryptography.hazmat.primitives.asymmetric import utils as asym_utils
    pub = ec.EllipticCurvePublicKey.from_encoded_point(
      ec.SECP256R1(), base64.urlsafe_b64decode(pad(keys["public_key"])))
    raw_sig = base64.urlsafe_b64decode(pad(signature))
    der_sig = asym_utils.encode_dss_signature(int.from_bytes(raw_sig[:32], "big"),
                                              int.from_bytes(raw_sig[32:], "big"))
    pub.verify(der_sig, f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))

  def test_ensure_vapid_keys_persists(self):
    class FakeParams:
      def __init__(self):
        self.store = {}

      def get(self, key):
        return self.store.get(key)

      def put(self, key, value):
        self.store[key] = value

    fake = FakeParams()
    keys = ensure_vapid_keys(fake)
    self.assertIn("private_key", keys)
    self.assertEqual(ensure_vapid_keys(fake), keys)  # second call reuses stored keys


if __name__ == "__main__":
  unittest.main()

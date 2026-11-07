"""Web Push (RFC 8291 / RFC 8292) without external push libraries.

Galaxy-inspired (StarPilot MIT). Only the `cryptography` package is required,
which this fork already ships for sunnylink backups. Subscriptions and VAPID
keys live in Params so the phone-side subscription survives reboots.
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils as asym_utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_VAPID_TTL_SECONDS = 12 * 3600
_PAYLOAD_RS = 4096  # aes128gcm record size


def _b64url_encode(data: bytes) -> str:
  return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
  pad = "=" * (-len(data) % 4)
  return base64.urlsafe_b64decode(data + pad)


def generate_vapid_keys() -> dict[str, str]:
  private_key = ec.generate_private_key(ec.SECP256R1())
  private_bytes = private_key.private_bytes(
    serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
  public_bytes = private_key.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
  return {
    "private_key": _b64url_encode(private_bytes),
    "public_key": _b64url_encode(public_bytes),
  }


def _load_private_key(private_b64: str) -> ec.EllipticCurvePrivateKey:
  return serialization.load_der_private_key(_b64url_decode(private_b64), password=None)


def _ecdh_shared_secret(private_key: ec.EllipticCurvePrivateKey, peer_public_b64: str) -> bytes:
  peer_public = ec.EllipticCurvePublicKey.from_encoded_point(
    ec.SECP256R1(), _b64url_decode(peer_public_b64))
  return private_key.exchange(ec.ECDH(), peer_public)


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
  return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt_payload(payload: bytes, p256dh: str, auth_secret: str) -> bytes:
  """One aes128gcm record; payload must fit a single record (< 4096 - 17 bytes)."""
  if len(payload) > _PAYLOAD_RS - 17:
    raise ValueError(f"payload too large for a single aes128gcm record: {len(payload)}")

  server_private = ec.generate_private_key(ec.SECP256R1())
  server_public = server_private.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
  client_public_bytes = _b64url_decode(p256dh)

  ecdh_secret = _ecdh_shared_secret(server_private, p256dh)
  auth_secret_bytes = _b64url_decode(auth_secret)
  # RFC 8291 section 2.2: ikm -> PRK via HKDF with the "WebPush: info" context
  prk_key = _hkdf(
    auth_secret_bytes, ecdh_secret,
    b"WebPush: info\x00" + client_public_bytes + server_public, 32)
  salt = os.urandom(16)
  cek = _hkdf(salt, prk_key, b"Content-Encoding: aes128gcm\x00", 16)
  nonce = _hkdf(salt, prk_key, b"Content-Encoding: nonce\x00", 12)

  ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
  header = salt + _PAYLOAD_RS.to_bytes(4, "big") + bytes([len(server_public)]) + server_public
  return header + ciphertext


def _jwt_b64(segment: dict[str, Any]) -> bytes:
  raw = json.dumps(segment, separators=(",", ":")).encode()
  return _b64url_encode(raw).encode()


def build_vapid_authorization(endpoint: str, vapid_keys: dict[str, str],
                              subject: str = "mailto:openpilot@localhost") -> str:
  """RFC 8292: ES256 JWT over the endpoint origin, key published alongside."""
  origin = endpoint.split("/")[2] if endpoint.count("/") >= 2 else endpoint
  claims = {"aud": f"https://{origin}", "exp": int(time.time()) + _VAPID_TTL_SECONDS, "sub": subject}
  signing_input = _jwt_b64({"typ": "JWT", "alg": "ES256"}) + b"." + _jwt_b64(claims)
  private_key = _load_private_key(vapid_keys["private_key"])
  der_signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
  r, s = asym_utils.decode_dss_signature(der_signature)
  raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
  jwt = signing_input + b"." + _b64url_encode(raw_signature).encode()
  return f"vapid t={jwt.decode()}, k={vapid_keys['public_key']}"


async def send_push(subscription: dict[str, Any], payload: str,
                    vapid_keys: dict[str, str], session) -> tuple[int, str]:
  """Send one encrypted push. `session` is an aiohttp ClientSession."""
  endpoint = str(subscription.get("endpoint", ""))
  keys = subscription.get("keys") or {}
  body = encrypt_payload(payload.encode(), str(keys.get("p256dh", "")), str(keys.get("auth", "")))
  headers = {
    "Authorization": build_vapid_authorization(endpoint, vapid_keys),
    "Content-Encoding": "aes128gcm",
    "Content-Type": "application/octet-stream",
    "TTL": "3600",
  }
  async with session.post(endpoint, data=body, headers=headers, timeout=15) as resp:
    return resp.status, (await resp.text())[:200]


def ensure_vapid_keys(params) -> dict[str, str]:
  """Load or lazily create the VAPID keypair (stored as JSON in Params)."""
  raw = params.get("WebPushVapidKeys")
  if raw:
    try:
      keys = json.loads(raw)
      if keys.get("private_key") and keys.get("public_key"):
        return keys
    except (ValueError, TypeError):
      pass
  keys = generate_vapid_keys()
  params.put("WebPushVapidKeys", json.dumps(keys))
  return keys

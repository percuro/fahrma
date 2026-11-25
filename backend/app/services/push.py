"""Web Push without a third-party account: VAPID (RFC 8292) and message encryption (RFC 8291).

The browser's push service (Google, Mozilla, Apple, Microsoft) only sees an encrypted
message and the VAPID signature of this instance. The key pair is generated on first use
and kept in the database, so self-hosting needs no configuration; VAPID_PRIVATE_KEY_FILE
replaces it with a key of the operator's own.
"""

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import ConfigError, PushSettings, get_push_settings
from app.models.push import InstanceKey, PushSubscription
from app.services.auth_service import utcnow

logger = logging.getLogger(__name__)

VAPID_KEY_NAME = "vapid_private_key"
# How long a push service keeps a message for a device that is offline
TTL_SECONDS = 24 * 3600
RECORD_SIZE = 4096


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- Keys -------------------------------------------------------------------


def private_key(db: Session, settings: PushSettings) -> ec.EllipticCurvePrivateKey:
    """The instance's VAPID key: from VAPID_PRIVATE_KEY_FILE, else generated once and stored."""
    if settings.key_file is not None:
        pem = settings.key_file.read_bytes()
    else:
        row = db.get(InstanceKey, VAPID_KEY_NAME)
        if row is None:
            generated = ec.generate_private_key(ec.SECP256R1())
            pem = generated.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
            db.add(InstanceKey(name=VAPID_KEY_NAME, value=pem.decode()))
            try:
                db.commit()
            except IntegrityError:
                # Another request stored one first
                db.rollback()
                pem = db.get(InstanceKey, VAPID_KEY_NAME).value.encode()
        else:
            pem = row.value.encode()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ConfigError("The VAPID key must be an EC key on the P-256 curve (prime256v1)")
    return key


def public_key_b64(key: ec.EllipticCurvePrivateKey) -> str:
    """The applicationServerKey for PushManager.subscribe() (uncompressed point, base64url)."""
    return b64url(
        key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )


def vapid_public_key(db: Session) -> str | None:
    settings = get_push_settings()
    return public_key_b64(private_key(db, settings)) if settings else None


# --- Subscriptions ----------------------------------------------------------


def endpoint_allowed(endpoint: str, settings: PushSettings) -> bool:
    """Only https URLs of known push services: the server never sends to an arbitrary address."""
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.port not in (None, 443) or parts.username or parts.password:
        return False
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in settings.allowed_hosts)


def keys_valid(p256dh: str, auth: str) -> bool:
    try:
        point = b64url_decode(p256dh)
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
        return len(point) == 65 and len(b64url_decode(auth)) == 16
    except (ValueError, TypeError):
        return False


# --- Encryption (RFC 8291, aes128gcm) and VAPID (RFC 8292) -----------------


def _hmac(key: bytes, data: bytes) -> bytes:
    mac = hmac.HMAC(key, hashes.SHA256())
    mac.update(data)
    return mac.finalize()


def encrypt(
    payload: bytes,
    p256dh: str,
    auth: str,
    *,
    salt: bytes | None = None,
    sender_key: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """The message body for one subscription: header (salt, record size, key) + one record."""
    ua_public = b64url_decode(p256dh)
    auth_secret = b64url_decode(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    as_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    as_public = as_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    shared_secret = as_key.exchange(ec.ECDH(), ua_key)
    # HKDF in its two steps, each with a single block of output
    prk_key = _hmac(auth_secret, shared_secret)
    ikm = _hmac(prk_key, b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    salt = salt or os.urandom(16)
    prk = _hmac(salt, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    # 0x02 marks the last (here: only) record
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    if len(ciphertext) > RECORD_SIZE:
        raise ValueError("Push message too long")
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + ciphertext


def vapid_authorization(key: ec.EllipticCurvePrivateKey, endpoint: str, subject: str, now: float) -> str:
    parts = urlsplit(endpoint)

    def segment(value: dict) -> str:
        return b64url(json.dumps(value, separators=(",", ":")).encode())

    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(now) + 12 * 3600, "sub": subject}
    signing_input = f"{segment({'typ': 'JWT', 'alg': 'ES256'})}.{segment(claims)}"
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    signature = b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={signing_input}.{signature}, k={public_key_b64(key)}"


# --- Sending ----------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    # A path of the app to open, e.g. "/g/3/reservation/12"
    url: str
    # Notifications with the same tag replace each other on the device
    tag: str


@dataclass(frozen=True)
class Target:
    subscription_id: int
    endpoint: str
    p256dh: str
    auth: str


def target_of(subscription: PushSubscription) -> Target:
    return Target(subscription.id, subscription.endpoint, subscription.p256dh, subscription.auth)


def post(endpoint: str, body: bytes, headers: dict[str, str]) -> int:
    """One request to the push service (replaced in tests)."""
    response = httpx.post(endpoint, content=body, headers=headers, timeout=10, follow_redirects=False)
    return response.status_code


def _write_file(settings: PushSettings, target: Target, message: Message) -> None:
    settings.directory.mkdir(parents=True, exist_ok=True)
    data = {"endpoint": target.endpoint, **message.__dict__}
    path = settings.directory / f"{time.time_ns()}-{target.subscription_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def deliver(db: Session, items: list[tuple[Target, Message]]) -> None:
    """Send the messages; subscriptions the push service no longer knows are removed."""
    settings = get_push_settings()
    if settings is None or not items:
        return
    key = private_key(db, settings) if settings.directory is None else None
    gone: list[int] = []
    delivered: list[int] = []
    for target, message in items:
        if not endpoint_allowed(target.endpoint, settings):
            continue
        try:
            if settings.directory is not None:
                _write_file(settings, target, message)
                status_code = 201
            else:
                payload = json.dumps(message.__dict__, ensure_ascii=False).encode()
                headers = {
                    "Authorization": vapid_authorization(key, target.endpoint, settings.subject, time.time()),
                    "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream",
                    "TTL": str(TTL_SECONDS),
                    "Urgency": "normal",
                }
                status_code = post(target.endpoint, encrypt(payload, target.p256dh, target.auth), headers)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("Push to %s failed: %s", urlsplit(target.endpoint).hostname, exc)
            continue
        if status_code in (404, 410):
            gone.append(target.subscription_id)
        elif 200 <= status_code < 300:
            delivered.append(target.subscription_id)
        else:
            logger.warning("Push to %s answered %s", urlsplit(target.endpoint).hostname, status_code)
    if gone:
        db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
    if delivered:
        db.execute(update(PushSubscription).where(PushSubscription.id.in_(delivered)).values(last_success_at=utcnow()))
    db.commit()

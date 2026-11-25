"""Web Push: encryption and VAPID, subscriptions per login, who gets which notification and when.

Messages are captured by replacing push.post and decrypted with http_ece, an implementation
independent of app/services/push.py, the way a browser would.
"""

import base64
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import http_ece
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from app.config import get_push_settings
from app.models.push import PushSubscription
from app.models.trip import Trip
from app.services import notification_service, push
from app.services.push import b64url, b64url_decode, encrypt, endpoint_allowed, vapid_authorization
from tests.support import PASSWORD
from tests.test_accounts import code
from tests.test_api import GroupSetupMixin


class Device:
    """A browser with its own push keys."""

    def __init__(self, name: str):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.endpoint = f"https://fcm.googleapis.com/fcm/send/{name}"

    def subscription(self, locale: str | None = "de") -> dict:
        public = self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": b64url(public), "auth": b64url(self.auth)},
            "locale": locale,
        }

    def read(self, body: bytes) -> dict:
        return json.loads(http_ece.decrypt(body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"))


class PushServiceStub:
    """Stands in for the push services: records requests, answers with a chosen status."""

    def __init__(self):
        self.sent: list[tuple[str, bytes, dict]] = []
        self.status = 201
        self._patch = mock.patch.object(push, "post", self.post)

    def post(self, endpoint: str, body: bytes, headers: dict) -> int:
        self.sent.append((endpoint, body, headers))
        return self.status

    def __enter__(self):
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()

    def messages(self, device: Device) -> list[dict]:
        return [device.read(body) for endpoint, body, _ in self.sent if endpoint == device.endpoint]


class CryptoTest(unittest.TestCase):
    def test_a_browser_can_decrypt_the_message(self):
        device = Device("crypto")
        sub = device.subscription()
        payload = json.dumps({"title": "Grüß dich", "body": "x" * 2000}).encode()
        body = encrypt(payload, sub["keys"]["p256dh"], sub["keys"]["auth"])
        self.assertEqual(device.read(body), json.loads(payload))
        # Header: 16 bytes salt, record size 4096, then the sender's 65-byte public key
        self.assertEqual(int.from_bytes(body[16:20], "big"), 4096)
        self.assertEqual(body[20], 65)
        # A fresh key and salt every time
        self.assertNotEqual(body, encrypt(payload, sub["keys"]["p256dh"], sub["keys"]["auth"]))

    def test_vapid_signature(self):
        key = ec.generate_private_key(ec.SECP256R1())
        header = vapid_authorization(
            key, "https://fcm.googleapis.com/fcm/send/abc", "mailto:ops@example.org", 1_000_000
        )
        token, public = header.removeprefix("vapid t=").split(", k=")
        signing_input, signature = token.rsplit(".", 1)
        raw = b64url_decode(signature)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        verifier = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64url_decode(public))
        verifier.verify(der, signing_input.encode(), ec.ECDSA(hashes.SHA256()))  # raises if wrong
        head, claims = (json.loads(base64.urlsafe_b64decode(p + "==")) for p in signing_input.split("."))
        self.assertEqual(head, {"typ": "JWT", "alg": "ES256"})
        self.assertEqual(
            claims, {"aud": "https://fcm.googleapis.com", "exp": 1_000_000 + 12 * 3600, "sub": "mailto:ops@example.org"}
        )

    def test_only_known_push_services(self):
        env = {"PUBLIC_URL": "https://cars.example.org", "PUSH": "", "PUSH_ALLOWED_HOSTS": "push.example.net"}
        with mock.patch.dict("os.environ", env):
            settings = get_push_settings()
        allowed = [
            "https://fcm.googleapis.com/fcm/send/x",
            "https://updates.push.services.mozilla.com/wpush/v2/x",
            "https://web.push.apple.com/x",
            "https://db5p.notify.windows.com/w/?token=x",
            "https://push.example.net/x",
        ]
        refused = [
            "http://fcm.googleapis.com/fcm/send/x",
            "https://fcm.googleapis.com.evil.example/x",
            "https://evilfcm.googleapis.com.example/x",
            "https://fcm.googleapis.com:8443/x",
            "https://user:pw@fcm.googleapis.com/x",
            "https://127.0.0.1/x",
            "https://localhost/x",
            "file:///etc/passwd",
        ]
        for url in allowed:
            self.assertTrue(endpoint_allowed(url, settings), url)
        for url in refused:
            self.assertFalse(endpoint_allowed(url, settings), url)


class PushMixin(GroupSetupMixin):
    def setUp(self):
        super().setUp()
        self.stub = PushServiceStub().__enter__()
        self.alex_device = Device("alex")
        self.sam_device = Device("sam")
        self.subscribe(self.alex, self.alex_device)
        self.subscribe(self.sam, self.sam_device)

    def tearDown(self):
        self.stub.__exit__()
        super().tearDown()

    def subscribe(self, client, device: Device, locale: str | None = "de"):
        response = client.post("/v1/account/push-subscription", json=device.subscription(locale))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def reserve(self, client, start, end, user_id, expect=201):
        response = client.post(
            f"{self.base}/reservations",
            json={"car_id": self.car_id, "user_id": user_id, "starts_at": start, "ends_at": end},
        )
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def db(self):
        return self.env.SessionLocal()


class SubscriptionTest(PushMixin, unittest.TestCase):
    def test_meta_offers_a_stable_key(self):
        first = self.alex.get("/v1/meta").json()["vapid_public_key"]
        self.assertEqual(len(b64url_decode(first)), 65)
        self.assertEqual(self.env.client(None).get("/v1/meta").json()["vapid_public_key"], first)

    def test_this_device_and_settings(self):
        state = self.alex.get("/v1/account/notifications").json()
        self.assertEqual((state["this_device"], state["devices"]), (True, 1))
        self.assertEqual(state["settings"]["lead_minutes"], 60)
        # Another login of alex does not receive anything yet
        other = self.env.client("alex")
        self.assertFalse(other.get("/v1/account/notifications").json()["this_device"])
        changed = {**state["settings"], "lead_minutes": 15, "settlements": False}
        self.assertEqual(self.alex.put("/v1/account/notifications", json=changed).json()["settings"], changed)
        self.assertEqual(self.alex.put("/v1/account/notifications", json={"lead_minutes": 30}).status_code, 422)

    def test_refuses_unknown_services_and_broken_keys(self):
        device = Device("x")
        unknown = {**device.subscription(), "endpoint": "https://push.example.org/x"}
        self.assertEqual(
            code(self.alex.post("/v1/account/push-subscription", json=unknown), 422), "push_service_unknown"
        )
        broken = device.subscription()
        broken["keys"]["p256dh"] = b64url(b"\x04" + b"\x01" * 64)  # not a point on the curve
        self.assertEqual(
            code(self.alex.post("/v1/account/push-subscription", json=broken), 422), "push_subscription_invalid"
        )

    def test_the_same_browser_moves_to_whoever_logs_in(self):
        self.subscribe(self.sam, self.alex_device)
        with self.db() as db:
            owners = {s.endpoint: s.user_id for s in db.query(PushSubscription)}
        self.assertEqual(owners[self.alex_device.endpoint], self.sam_id)
        self.assertFalse(self.alex.get("/v1/account/notifications").json()["this_device"])

    def test_unsubscribe_and_logout(self):
        response = self.alex.request(
            "DELETE", "/v1/account/push-subscription", json={"endpoint": self.alex_device.endpoint}
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.alex.get("/v1/account/notifications").json()["devices"], 0)
        self.assertEqual(self.sam.post("/v1/auth/logout").status_code, 204)
        with self.db() as db:
            self.assertEqual(db.query(PushSubscription).count(), 0)

    def test_test_message_to_this_device(self):
        other = self.env.client("alex")
        self.assertEqual(code(other.post("/v1/account/push-test"), 409), "push_not_subscribed")
        self.assertEqual(self.alex.post("/v1/account/push-test").status_code, 202)
        [message] = self.stub.messages(self.alex_device)
        self.assertEqual(message["title"], "Benachrichtigungen funktionieren")
        self.assertEqual(self.stub.messages(self.sam_device), [])
        _endpoint, _body, headers = self.stub.sent[0]
        self.assertEqual(headers["Content-Encoding"], "aes128gcm")
        self.assertTrue(headers["Authorization"].startswith("vapid t="))

    def test_gone_subscriptions_are_removed(self):
        self.stub.status = 410
        self.alex.post("/v1/account/push-test")
        self.assertEqual(self.alex.get("/v1/account/notifications").json()["devices"], 0)

    def test_switched_off(self):
        with mock.patch.dict("os.environ", {"PUSH": "off"}):
            self.assertIsNone(self.alex.get("/v1/meta").json()["vapid_public_key"])
            response = self.alex.post("/v1/account/push-subscription", json=Device("y").subscription())
            self.assertEqual(code(response, 409), "push_disabled")
            self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.sam_id)
        self.assertEqual(self.stub.sent, [])

    def test_push_dir_writes_files_instead(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict("os.environ", {"PUSH_DIR": directory}):
            self.alex.post("/v1/account/push-test")
            [file] = Path(directory).glob("*.json")
            written = json.loads(file.read_text())
        self.assertEqual((written["endpoint"], written["url"]), (self.alex_device.endpoint, "/profile"))
        self.assertEqual(self.stub.sent, [])

    def test_deleting_the_account_removes_everything(self):
        self.assertEqual(self.sam.request("DELETE", "/v1/account", json={"password": PASSWORD}).status_code, 204)
        with self.db() as db:
            self.assertEqual([s.user_id for s in db.query(PushSubscription)], [self.alex_id])
        mine = self.alex.get("/v1/account/export.json").json()["notifications"]
        self.assertEqual(len(mine["devices"]), 1)
        self.assertEqual(mine["devices"][0]["push_service"], "fcm.googleapis.com")


class EventTest(PushMixin, unittest.TestCase):
    def test_reservation_for_someone_else(self):
        created = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.sam_id)
        [message] = self.stub.messages(self.sam_device)
        self.assertEqual(message["title"], "Reservierung für dich")
        self.assertEqual(message["body"], "Alex hat Test car für dich reserviert: Di 01.12., 10:00–12:00.")
        self.assertEqual(message["url"], f"/g/{self.gid}/reservation/{created['id']}")
        # Nobody is told about their own doing
        self.assertEqual(self.stub.messages(self.alex_device), [])
        self.reserve(self.sam, "2026-12-02T10:00", "2026-12-02T12:00", self.sam_id)
        self.assertEqual(len(self.stub.messages(self.sam_device)), 1)

    def test_change_move_and_cancel(self):
        created = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.sam_id)
        url = f"{self.base}/reservations/{created['id']}"
        body = {
            "car_id": self.car_id,
            "user_id": self.sam_id,
            "starts_at": "2026-12-01T11:00",
            "ends_at": "2026-12-01T13:00",
        }
        self.alex.put(url, json=body)
        self.assertEqual(self.stub.messages(self.sam_device)[-1]["title"], "Reservierung geändert")
        # Moved to alex himself: for sam it is gone
        self.alex.put(url, json={**body, "user_id": self.alex_id})
        self.assertEqual(self.stub.messages(self.sam_device)[-1]["title"], "Reservierung gelöscht")
        self.alex.put(url, json=body)
        self.assertEqual(self.alex.delete(url).status_code, 204)
        last = self.stub.messages(self.sam_device)[-1]
        self.assertEqual((last["title"], last["url"]), ("Reservierung gelöscht", f"/g/{self.gid}/calendar"))
        # Refused: nothing goes out
        count = len(self.stub.sent)
        self.reserve(self.alex, "2026-11-01T10:00", "2026-11-01T12:00", self.sam_id, expect=422)
        self.assertEqual(len(self.stub.sent), count)

    def test_language_and_settings(self):
        self.subscribe(self.sam, self.sam_device, locale="en")
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.sam_id)
        self.assertEqual(
            self.stub.messages(self.sam_device)[-1]["body"], "Alex reserved Test car for you: Tue 01/12, 10:00–12:00."
        )
        self.sam.put("/v1/account/notifications", json={"reservation_changes": False})
        self.reserve(self.alex, "2026-12-02T10:00", "2026-12-02T12:00", self.sam_id)
        self.assertEqual(len(self.stub.messages(self.sam_device)), 1)

    def test_settlement_reaches_the_others(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        settlement = self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-20"})
        self.assertEqual(settlement.status_code, 201, settlement.text)
        [message] = self.stub.messages(self.sam_device)
        self.assertEqual(message["body"], "Alex hat in „Test group“ abgerechnet.")
        self.assertNotIn("€", json.dumps(message))
        self.assertEqual(self.stub.messages(self.alex_device), [])


class ReminderTest(PushMixin, unittest.TestCase):
    def run_at(self, moment: str) -> list[dict]:
        with self.db() as db:
            items = notification_service.run_due(db, datetime.fromisoformat(moment).replace(tzinfo=UTC))
            push.deliver(db, items)
        return [message for _target, message in items]

    def test_reminder_once_at_the_lead_time(self):
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.sam_id)
        self.stub.sent.clear()
        self.assertEqual(self.run_at("2026-12-01T08:59"), [])
        [message] = self.run_at("2026-12-01T09:00")
        self.assertEqual(message.title, "Deine Reservierung beginnt bald")
        self.assertEqual(self.run_at("2026-12-01T09:01"), [])
        self.assertEqual(len(self.stub.messages(self.sam_device)), 1)

    def test_moving_a_reservation_reminds_again(self):
        created = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.sam_id)
        self.assertEqual(len(self.run_at("2026-12-01T09:30")), 1)
        body = {
            "car_id": self.car_id,
            "user_id": self.sam_id,
            "starts_at": "2026-12-01T10:30",
            "ends_at": "2026-12-01T12:00",
        }
        self.alex.put(f"{self.base}/reservations/{created['id']}", json=body)
        self.assertEqual(len(self.run_at("2026-12-01T09:45")), 1)

    def test_own_settings(self):
        self.sam.put("/v1/account/notifications", json={"lead_minutes": 15})
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.sam_id)
        self.assertEqual(self.run_at("2026-12-01T09:30"), [])
        self.assertEqual(len(self.run_at("2026-12-01T09:45")), 1)
        self.sam.put("/v1/account/notifications", json={"reservation_reminder": False})
        self.reserve(self.alex, "2026-12-02T10:00", "2026-12-02T12:00", self.sam_id)
        self.assertEqual(self.run_at("2026-12-02T09:50"), [])

    def test_no_reminder_without_a_device_or_after_leaving(self):
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", self.alex_id)
        self.alex.request("DELETE", "/v1/account/push-subscription", json={"endpoint": self.alex_device.endpoint})
        self.assertEqual(self.run_at("2026-12-01T09:30"), [])
        self.reserve(self.alex, "2026-12-03T10:00", "2026-12-03T12:00", self.sam_id)
        self.alex.patch(f"{self.base}/members/{self.sam_id}", json={"active": False})
        self.assertEqual(self.run_at("2026-12-03T09:30"), [])

    def test_open_trip(self):
        trip = self.trip(self.sam, 10000, None, [(self.sam_id, 1)])
        with self.db() as db:
            db.get(Trip, trip["id"]).created_at = datetime(2026, 11, 24, 8, 0)
            db.commit()
        self.assertEqual(self.run_at("2026-11-24T19:59"), [])
        [message] = self.run_at("2026-11-24T20:00")
        self.assertEqual((message.title, message.url), ("Fahrt läuft noch", f"/g/{self.gid}"))
        self.assertIn("10.000 km", message.body)
        self.assertEqual(self.run_at("2026-11-25T08:00"), [])

    def test_open_trip_when_the_reservation_is_over(self):
        trip = self.trip(self.sam, 10000, None, [(self.sam_id, 1)])
        self.reserve(self.sam, "2026-11-24T13:00", "2026-11-24T15:00", self.sam_id)
        with self.db() as db:
            db.get(Trip, trip["id"]).created_at = datetime(2026, 11, 24, 13, 0)
            db.commit()
        self.assertEqual(self.run_at("2026-11-24T14:59"), [])
        self.assertEqual(len(self.run_at("2026-11-24T15:00")), 1)


if __name__ == "__main__":
    unittest.main()

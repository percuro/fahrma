"""Security log: what is written, what is never written, who sees what."""

import json
import unittest
from datetime import timedelta
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.models.security_event import SecurityEvent
from app.services import security_log
from app.services.client_address import ip_prefix
from app.services.login_rate_limiter import login_rate_limiter
from tests.oidc_fake import ISSUER
from tests.support import HEADERS, PASSWORD, ApiTestEnvironment, accept
from tests.test_oidc_flows import OidcTestCase
from tests.test_plans import HostingTestCase

NEW_PASSWORD = "ein-neues-passwort-456"
OPERATOR_TOKEN = "o" * 40


class IpPrefixTest(unittest.TestCase):
    def test_shortens_addresses(self):
        self.assertEqual(ip_prefix("203.0.113.7"), "203.0.113.0/24")
        self.assertEqual(ip_prefix("2001:db8:1:2::5"), "2001:db8:1::/48")
        self.assertEqual(ip_prefix("::ffff:198.51.100.9"), "198.51.100.0/24")
        self.assertIsNone(ip_prefix("testclient"))
        self.assertIsNone(ip_prefix("unknown"))
        self.assertIsNone(ip_prefix(None))


class SecurityLogTestCase(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()
        self.root_user = self.env.create_user("root", role="admin")
        self.sam_user = self.env.create_user("sam")
        self.root = self.env.client("root")
        security_log.reset_prune_timer()

    def tearDown(self):
        self.env.close()

    def events(self) -> list[SecurityEvent]:
        db = self.env.SessionLocal()
        try:
            return list(db.query(SecurityEvent).order_by(SecurityEvent.id))
        finally:
            db.close()

    def names(self) -> list[str]:
        return [event.event for event in self.events()]

    def last(self, name: str) -> SecurityEvent:
        matching = [event for event in self.events() if event.event == name]
        self.assertTrue(matching, f"no {name} in {self.names()}")
        return matching[-1]

    def remote(self, ip: str) -> TestClient:
        return TestClient(app, headers=HEADERS, client=(ip, 50000))


class LoginEventsTest(SecurityLogTestCase):
    def test_login_success_and_failure(self):
        login = self.last("auth.login")
        self.assertEqual((login.target_username, security_log.details_of(login)), ("root", {"method": "password"}))
        # Successful logins store no address
        self.assertIsNone(login.ip_prefix)
        remote = self.remote("203.0.113.7")
        remote.post("/v1/auth/login", json={"username": "sam", "password": "falsch-falsch"})
        remote.post("/v1/auth/login", json={"username": "nobody-here", "password": "falsch-falsch"})
        failed = [event for event in self.events() if event.event == "auth.login_failed"]
        # A mistyped or made-up username is never stored, not even in the details
        self.assertEqual([(event.target_username, event.ip_prefix) for event in failed], [("sam", "203.0.113.0/24")])
        self.assertNotIn("nobody-here", json.dumps([[e.details, e.target_username] for e in self.events()]))

    def test_block_is_logged_once(self):
        remote = self.remote("198.51.100.20")
        for _ in range(login_rate_limiter.account_limit + 3):
            remote.post("/v1/auth/login", json={"username": "sam", "password": "falsch-falsch"})
        blocks = [event for event in self.events() if event.event == "auth.rate_limited"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(
            (blocks[0].target_username, blocks[0].ip_prefix, security_log.details_of(blocks[0])),
            ("sam", "198.51.100.0/24", {"limiter": "login"}),
        )
        # Refused requests while blocked are not logged again
        self.assertEqual(self.names().count("auth.login_failed"), login_rate_limiter.account_limit)

    def test_wrong_password_when_confirming(self):
        sam = self.env.client("sam")
        sam.request("DELETE", "/v1/account", json={"password": "falsch-falsch"})
        event = self.last("auth.confirm_failed")
        self.assertEqual((event.actor_username, event.target_username), ("sam", "sam"))

    def test_operator_tokens_are_limited_and_the_block_logged(self):
        with mock.patch.dict("os.environ", {"OPERATOR_TOKEN": OPERATOR_TOKEN}):
            remote = self.remote("192.0.2.50")
            wrong = {"Authorization": "Bearer wrong"}
            statuses = [remote.get("/v1/operator/groups", headers=wrong).status_code for _ in range(21)]
            self.assertEqual(statuses[:20], [401] * 20)
            self.assertEqual(statuses[20], 429)
            right = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}
            self.assertEqual(self.remote("192.0.2.51").get("/v1/operator/groups", headers=right).status_code, 200)
        block = self.last("auth.rate_limited")
        self.assertEqual((block.ip_prefix, security_log.details_of(block)), ("192.0.2.0/24", {"limiter": "operator"}))


class AccountEventsTest(SecurityLogTestCase):
    def test_each_change_writes_its_event(self):
        sam = self.env.client("sam")
        other_device = self.env.client("sam")
        self.assertEqual(
            sam.post(
                "/v1/account/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
            ).status_code,
            204,
        )
        self.assertEqual(other_device.get("/v1/auth/me").status_code, 401)
        self.env.client("sam", NEW_PASSWORD)
        sam.post("/v1/account/sessions/revoke-others")
        self.assertEqual(security_log.details_of(self.last("account.sessions_revoked")), {"count": 1})

        sam_id = self.sam_user.id
        self.root.patch(f"/v1/admin/users/{sam_id}", json={"role": "admin"})
        self.root.patch(f"/v1/admin/users/{sam_id}", json={"role": "user"})
        self.root.patch(f"/v1/admin/users/{sam_id}", json={"is_active": False})
        self.root.patch(f"/v1/admin/users/{sam_id}", json={"is_active": True})
        self.root.post(f"/v1/admin/users/{sam_id}/password-reset")
        invitation = self.root.post("/v1/admin/invitations", json={"role": "user"}).json()
        self.root.delete(f"/v1/admin/invitations/{invitation['id']}")
        self.root.delete(f"/v1/admin/users/{sam_id}")

        names = self.names()
        for name in (
            "account.password_changed",
            "account.sessions_revoked",
            "admin.role_changed",
            "admin.deactivated",
            "admin.reactivated",
            "account.reset_link_created",
            "admin.invite_created",
            "admin.invite_revoked",
            "account.deleted",
        ):
            self.assertIn(name, names)
        role = [e for e in self.events() if e.event == "admin.role_changed"]
        self.assertEqual(
            [security_log.details_of(e) for e in role],
            [{"before": "user", "after": "admin"}, {"before": "admin", "after": "user"}],
        )
        deleted = self.last("account.deleted")
        # The name stays readable although the account is anonymized
        self.assertEqual(
            (deleted.actor_username, deleted.target_username, security_log.details_of(deleted)),
            ("root", "sam", {"by": "admin"}),
        )
        self.assertEqual(self.last("account.password_changed").target_username, "sam")

    def test_reset_link_used(self):
        url = self.root.post(f"/v1/admin/users/{self.sam_user.id}/password-reset").json()["url"]
        guest = self.env.client(username=None)
        self.assertEqual(accept(guest, url, password=NEW_PASSWORD).status_code, 200)
        event = self.last("account.reset_used")
        self.assertEqual((event.target_username, security_log.details_of(event)), ("sam", {"method": "password"}))

    def test_new_accounts_say_how_they_came(self):
        invitation = self.root.post("/v1/admin/invitations", json={"role": "user"}).json()
        guest = self.env.client(username=None)
        accept(guest, invitation["url"], username="mia", password=PASSWORD)
        created = self.last("account.created")
        self.assertEqual((created.target_username, security_log.details_of(created)), ("mia", {"via": "invitation"}))
        with mock.patch.dict("os.environ", {"REGISTRATION": "open"}):
            guest = self.env.client(username=None)
            guest.post("/v1/auth/register", json={"username": "noa", "password": PASSWORD})
        self.assertEqual(security_log.details_of(self.last("account.created")), {"via": "register"})

    def test_no_secrets_in_the_log(self):
        sam = self.env.client("sam")
        sam.post("/v1/account/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        url = self.root.post(f"/v1/admin/users/{self.sam_user.id}/password-reset").json()["url"]
        token = url.split("#", 1)[1]
        text = json.dumps([[e.event, e.details, e.target_username, e.actor_username] for e in self.events()])
        for secret in (PASSWORD, NEW_PASSWORD, token):
            self.assertNotIn(secret, text)


class ViewsTest(SecurityLogTestCase):
    def test_admin_pages_and_filters(self):
        remote = self.remote("203.0.113.9")
        for _ in range(3):
            remote.post("/v1/auth/login", json={"username": "sam", "password": "falsch-falsch"})
        page = self.root.get("/v1/admin/security-log", params={"limit": 2}).json()
        self.assertEqual((len(page["events"]), page["retention_days"]), (2, 180))
        self.assertIsNotNone(page["next_before_id"])
        older = self.root.get("/v1/admin/security-log", params={"before_id": page["next_before_id"]}).json()
        self.assertTrue(all(event["id"] < page["next_before_id"] for event in older["events"]))
        failures = self.root.get("/v1/admin/security-log", params={"failures": "true"}).json()["events"]
        self.assertEqual({event["event"] for event in failures}, {"auth.login_failed"})
        self.assertEqual(failures[0]["ip_prefix"], "203.0.113.0/24")
        only_root = self.root.get("/v1/admin/security-log", params={"user_id": self.root_user.id}).json()["events"]
        self.assertEqual({event["target_username"] for event in only_root}, {"root"})

    def test_only_admins(self):
        sam = self.env.client("sam")
        self.assertEqual(sam.get("/v1/admin/security-log").status_code, 403)

    def test_own_view_names_no_admin(self):
        self.root.patch(f"/v1/admin/users/{self.sam_user.id}", json={"role": "admin"})
        self.remote("203.0.113.30").post("/v1/auth/login", json={"username": "sam", "password": "falsch-falsch"})
        sam = self.env.client("sam")
        events = sam.get("/v1/account/security-log").json()["events"]
        self.assertEqual(
            [event["event"] for event in events],
            ["auth.login", "auth.login_failed", "admin.role_changed", "account.created"],
        )
        self.assertEqual(events[1]["ip_prefix"], "203.0.113.0/24")
        self.assertEqual(events[2]["actor"], "admin")
        self.assertNotIn("root", json.dumps(events))
        # What root did to sam is not in root's own list
        own = self.root.get("/v1/account/security-log").json()["events"]
        self.assertEqual({event["event"] for event in own}, {"auth.login", "account.created"})

    def test_paging_of_the_own_view(self):
        for _ in range(3):
            self.env.client("sam")
        sam = self.env.client("sam")
        page = sam.get("/v1/account/security-log", params={"limit": 2}).json()
        self.assertEqual(len(page["events"]), 2)
        rest = sam.get("/v1/account/security-log", params={"before_id": page["next_before_id"]}).json()
        # Four logins and the creation of the account
        self.assertEqual((len(rest["events"]), rest["next_before_id"]), (3, None))

    def test_in_my_data(self):
        sam = self.env.client("sam")
        exported = sam.get("/v1/account/export.json").json()["security_log"]
        self.assertEqual([row["event"] for row in exported], ["auth.login", "account.created"])
        self.assertEqual(exported[0]["actor"], None)


class RetentionTest(SecurityLogTestCase):
    def age(self, days: int) -> None:
        db = self.env.SessionLocal()
        try:
            db.query(SecurityEvent).update({SecurityEvent.created_at: security_log.utcnow() - timedelta(days=days)})
            db.commit()
        finally:
            db.close()

    def test_old_entries_are_pruned(self):
        self.age(179)
        security_log.reset_prune_timer()
        self.env.client("sam")
        self.assertIn("auth.login", self.names())
        kept = len(self.events())
        self.age(181)
        security_log.reset_prune_timer()
        self.env.client("sam")
        self.assertEqual(len(self.events()), 1)
        self.assertGreater(kept, 1)

    def test_shorter_retention(self):
        self.age(31)
        security_log.reset_prune_timer()
        with mock.patch.dict("os.environ", {"SECURITY_LOG_DAYS": "30"}):
            self.env.client("sam")
        self.assertEqual(len(self.events()), 1)


class SetupEventsTest(unittest.TestCase):
    def test_wrong_token_is_logged_with_the_address(self):
        from app.services import setup_service

        env = ApiTestEnvironment()
        self.addCleanup(env.close)
        token = setup_service.issue_token()
        self.addCleanup(setup_service.clear_token)
        remote = TestClient(app, headers=HEADERS, client=("203.0.113.40", 50000))
        body = {"username": "first", "password": PASSWORD}
        remote.post("/v1/setup", json={**body, "token": "wrong"})
        self.assertEqual(remote.post("/v1/setup", json={**body, "token": token}).status_code, 200)
        db = env.SessionLocal()
        try:
            events = [(e.event, e.ip_prefix, security_log.details_of(e)) for e in db.query(SecurityEvent)]
        finally:
            db.close()
        self.assertEqual(
            events,
            [
                ("setup.failed", "203.0.113.0/24", {}),
                ("account.created", None, {"via": "setup", "role": "admin"}),
                ("auth.login", None, {"method": "password"}),
            ],
        )


class OidcEventsTest(OidcTestCase):
    def setUp(self):
        super().setUp()
        self.env.create_user("alex", role="admin")

    def names(self):
        return [event.event for event in self.query(SecurityEvent)]

    def test_link_login_unlink_and_failures(self):
        alex = self.env.client("alex")
        url = self.start(alex, purpose="link", password=PASSWORD, return_to="/profile")
        self.finish(alex, url, "sub-anna")
        guest = self.guest()
        self.sign_in(guest, "sub-anna")
        self.assertEqual(alex.request("DELETE", "/v1/account/oidc", json={"password": PASSWORD}).status_code, 204)
        self.sign_in(self.guest(), "sub-ben")
        events = self.query(SecurityEvent)
        self.assertEqual(
            [e.event for e in events],
            [
                "account.created",
                "auth.login",
                "account.oidc_linked",
                "auth.login",
                "account.oidc_unlinked",
                "auth.oidc_failed",
            ],
        )
        self.assertEqual(security_log.details_of(events[3]), {"method": "oidc"})
        self.assertEqual((events[5].ip_prefix, security_log.details_of(events[5])), (None, {"code": "oidc_no_account"}))
        self.assertNotIn(ISSUER, json.dumps([e.details for e in events]))


class PlanEventsTest(HostingTestCase):
    env_values = {"OPERATOR_TOKEN": OPERATOR_TOKEN}

    def changes(self):
        db = self.env.SessionLocal()
        try:
            events = db.query(SecurityEvent).filter_by(event="plan.changed").order_by(SecurityEvent.id).all()
            return [(e.actor_username, security_log.details_of(e)) for e in events]
        finally:
            db.close()

    def test_admin_and_operator_changes(self):
        self.set_plan("plus", until="2027-01-31", note="Invoice 1")
        # Only the note changed: not a plan change
        self.set_plan("plus", until="2027-01-31", note="Invoice 1, paid")
        operator = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}
        body = {"plan": None, "until": None, "note": None}
        response = self.env.client(username=None).put(
            f"/v1/operator/groups/{self.gid}/plan", json=body, headers=operator
        )
        self.assertEqual(response.status_code, 200, response.text)
        group = {"group_id": self.gid, "group": "Test group"}
        self.assertEqual(
            self.changes(),
            [
                ("root", {**group, "by": "admin", "plan": "plus", "until": "2027-01-31"}),
                (None, {**group, "by": "operator", "plan": None, "until": None}),
            ],
        )


class OwnViewOfAdminsTest(HostingTestCase):
    def test_admin_work_is_not_in_the_own_list(self):
        self.set_plan("plus")
        own = self.root.get("/v1/account/security-log").json()["events"]
        self.assertEqual({event["event"] for event in own}, {"auth.login", "account.created"})

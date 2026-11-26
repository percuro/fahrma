"""Hosting: plans per group, the billing link and the operator API."""

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models.group import Group
from app.models.user import User
from app.services import billing_link
from tests.support import PASSWORD, accept
from tests.test_accounts import code
from tests.test_api import GroupSetupMixin

PLANS = {
    "default": "free",
    "plans": [
        {
            "id": "free",
            "name": {"de": "Gratis", "en": "Free"},
            "members_per_group": 3,
            "cars_per_group": 1,
            "receipt_mb_per_group": 1,
        },
        {"id": "plus", "name": "Plus", "members_per_group": 25, "cars_per_group": 5},
        {"id": "club", "name": "Club"},
    ],
}
TOKEN = "t" * 40
PAST, FUTURE = "2000-01-01", "2999-12-31"


class PlanFile:
    """A PLANS_FILE in a temporary directory; ``write`` replaces its content."""

    def __init__(self, content=PLANS):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "plans.json"
        self.write(content)

    def write(self, content) -> None:
        self.path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        # A new modification time, so the cached file is read again
        stat = self.path.stat()
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    def close(self) -> None:
        self.directory.cleanup()


class PlanConfigTests(unittest.TestCase):
    def setUp(self):
        self.file = PlanFile()
        self.addCleanup(self.file.close)
        env = {"PLANS_FILE": "", "MAX_MEMBERS_PER_GROUP": "", "MAX_CARS_PER_GROUP": "", "BILLING_URL": ""}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def plans(self, content):
        self.file.write(content)
        with mock.patch.dict(os.environ, {"PLANS_FILE": str(self.file.path)}):
            return config.get_plans()

    def test_without_file_one_plan_with_the_max_limits(self):
        with mock.patch.dict(os.environ, {"MAX_CARS_PER_GROUP": "2"}):
            plans = config.get_plans()
        self.assertFalse(plans.configured)
        self.assertEqual(list(plans.plans), ["default"])
        self.assertEqual((plans.default_plan.cars_per_group, plans.default_plan.members_per_group), (2, None))

    def test_file(self):
        plans = self.plans(PLANS)
        self.assertTrue(plans.configured)
        self.assertEqual(list(plans.plans), ["free", "plus", "club"])
        self.assertEqual(plans.default, "free")
        self.assertEqual(plans.plans["free"].name, {"de": "Gratis", "en": "Free"})
        self.assertEqual((plans.plans["club"].members_per_group, plans.plans["club"].cars_per_group), (None, None))

    def test_zero_means_unlimited(self):
        content = {"default": "a", "plans": [{"id": "a", "name": "A", "cars_per_group": 0}]}
        self.assertIsNone(self.plans(content).plans["a"].cars_per_group)

    def test_invalid_files(self):
        one = {"id": "a", "name": "A"}
        for content in (
            "not json",
            [],
            {"default": "a", "plans": []},
            {"default": "b", "plans": [one]},
            {"default": "a", "plans": [one, one]},
            {"default": "a", "plans": [one], "extra": 1},
            {"default": "a", "plans": [{**one, "cars": 1}]},
            {"default": "a", "plans": [{**one, "cars_per_group": -1}]},
            {"default": "a", "plans": [{**one, "cars_per_group": True}]},
            {"default": "a", "plans": [{**one, "cars_per_group": "2"}]},
            {"default": "A", "plans": [{**one, "id": "A"}]},
            {"default": "a", "plans": [{"id": "a"}]},
            {"default": "a", "plans": [{"id": "a", "name": ""}]},
            {"default": "a", "plans": [{"id": "a", "name": {"deutsch": "A"}}]},
        ):
            with self.subTest(content=content), self.assertRaises(config.ConfigError):
                self.plans(content)

    def test_missing_file(self):
        with (
            mock.patch.dict(os.environ, {"PLANS_FILE": "/nonexistent/plans.json"}),
            self.assertRaises(config.ConfigError),
        ):
            config.get_plans()

    def test_group_limits_not_twice(self):
        env = {"PLANS_FILE": str(self.file.path), "MAX_CARS_PER_GROUP": "2"}
        with mock.patch.dict(os.environ, env), self.assertRaises(config.ConfigError):
            config.get_plans()

    def test_file_broken_while_running_keeps_the_last_valid_plans(self):
        self.assertEqual(self.plans(PLANS).default, "free")
        with self.assertLogs("app.config", "ERROR") as logs:
            self.assertEqual(self.plans("{broken").default, "free")
            # Reported once, not on every request
            self.assertEqual(self.plans("{broken").default, "free")
        self.assertEqual(len(logs.records), 1)
        with mock.patch.dict(os.environ, {"PLANS_FILE": str(self.file.path)}), self.assertRaises(config.ConfigError):
            config.get_plans(strict=True)
        self.assertEqual(self.plans({**PLANS, "default": "plus"}).default, "plus")

    def test_changed_file_is_read_again(self):
        self.assertEqual(self.plans(PLANS).default, "free")
        self.assertEqual(self.plans({**PLANS, "default": "plus"}).default, "plus")

    def test_billing_url(self):
        for bad in ("example.org/plans", "https://example.org/plans#x"):
            with mock.patch.dict(os.environ, {"BILLING_URL": bad}), self.assertRaises(config.ConfigError):
                config.get_billing_url()
        with mock.patch.dict(os.environ, {"BILLING_URL": "https://example.org/plans"}):
            self.assertEqual(config.get_billing_url(), "https://example.org/plans")

    def test_operator_token(self):
        with mock.patch.dict(os.environ, {"OPERATOR_TOKEN": "", "OPERATOR_TOKEN_FILE": ""}):
            self.assertIsNone(config.get_operator_token())
        with (
            mock.patch.dict(os.environ, {"OPERATOR_TOKEN": "short", "OPERATOR_TOKEN_FILE": ""}),
            self.assertRaises(config.ConfigError),
        ):
            config.get_operator_token()
        token_file = Path(self.file.directory.name) / "token"
        token_file.write_text(TOKEN + "\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"OPERATOR_TOKEN": "x" * 40, "OPERATOR_TOKEN_FILE": str(token_file)}):
            self.assertEqual(config.get_operator_token(), TOKEN)


class HostingTestCase(GroupSetupMixin, unittest.TestCase):
    """The group of GroupSetupMixin (alex admin, sam member, one car) on an instance with plans."""

    env_values: dict = {}

    def setUp(self):
        super().setUp()
        self.file = PlanFile()
        self.addCleanup(self.file.close)
        patcher = mock.patch.dict(os.environ, {"PLANS_FILE": str(self.file.path), **self.env_values})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env.create_user("root", role="admin")
        self.root = self.env.client("root")

    def set_plan(self, plan, until=None, note=None):
        response = self.root.put(f"/v1/admin/groups/{self.gid}/plan", json={"plan": plan, "until": until, "note": note})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def add_car(self, name="Second"):
        return self.alex.post(f"{self.base}/cars", json={"name": name, "start_odometer_km": 0})


class PlanTests(HostingTestCase):
    def test_meta(self):
        meta = self.env.client(None).get("/v1/meta").json()
        self.assertEqual([plan["id"] for plan in meta["plans"]], ["free", "plus", "club"])
        self.assertEqual(meta["plans"][0]["name"], {"de": "Gratis", "en": "Free"})
        self.assertEqual(meta["default_plan"], "free")
        self.assertEqual(
            meta["limits"],
            {"groups_per_user": None, "members_per_group": 3, "cars_per_group": 1, "receipt_mb_per_group": 1},
        )
        self.assertFalse(meta["billing"])

    def test_meta_without_plans(self):
        with mock.patch.dict(os.environ, {"PLANS_FILE": ""}):
            meta = self.env.client(None).get("/v1/meta").json()
        self.assertIsNone(meta["plans"])
        self.assertIsNone(meta["default_plan"])
        self.assertFalse(meta["billing"])

    def test_group_shows_its_plan_and_usage(self):
        plan = self.alex.get(self.base).json()["plan"]
        self.assertEqual(plan["id"], "free")
        self.assertEqual(plan["usage"], {"members_per_group": 2, "cars_per_group": 1, "receipt_mb_per_group": 0.0})
        self.assertEqual((plan["members_per_group"], plan["cars_per_group"], plan["until"]), (3, 1, None))
        self.set_plan("plus", until=FUTURE, note="Invoice 2026-001")
        group = self.sam.get(self.base).json()
        self.assertEqual((group["plan"]["id"], group["plan"]["until"]), ("plus", FUTURE))
        self.assertNotIn("Invoice", json.dumps(group))

    def test_limits_follow_the_plan(self):
        second = self.add_car()
        self.assertEqual(code(second, 409), "limit_reached")
        self.assertEqual(second.json()["detail"]["params"], {"limit": "cars_per_group", "max": 1, "plan": "free"})
        self.set_plan("plus")
        self.assertEqual(self.add_car().status_code, 201)
        self.set_plan("club")
        for number in range(6):
            self.assertEqual(self.add_car(f"Car {number}").status_code, 201)

    def test_expired_plan_falls_back_to_the_default(self):
        self.set_plan("plus", until=PAST)
        self.assertEqual(code(self.add_car(), 409), "limit_reached")
        self.assertEqual(self.alex.get(self.base).json()["plan"]["id"], "free")
        self.set_plan("plus", until=FUTURE)
        self.assertEqual(self.add_car().status_code, 201)

    def test_plan_removed_from_the_file_falls_back_to_the_default(self):
        self.set_plan("plus")
        self.file.write({"default": "free", "plans": [PLANS["plans"][0]]})
        self.assertEqual(self.alex.get(self.base).json()["plan"]["id"], "free")
        self.assertEqual(code(self.add_car(), 409), "limit_reached")

    def test_a_smaller_plan_keeps_everything(self):
        self.set_plan("plus")
        second = self.add_car().json()
        self.set_plan(None)
        # Both cars stay usable; only adding is refused
        cars = self.alex.get(f"{self.base}/cars").json()
        self.assertEqual(len([car for car in cars if not car["archived"]]), 2)
        trip = self.sam.post(
            f"{self.base}/trips",
            json={"car_id": second["id"], "date": "2026-11-10", "start_km": 0, "end_km": 50,
                  "shares": [{"user_id": self.sam_id, "weight": 1}], "external": []},
        )  # fmt: skip
        self.assertEqual(trip.status_code, 201, trip.text)
        self.assertEqual(code(self.add_car("Third"), 409), "limit_reached")
        # Archiving one and bringing it back counts like adding
        body = {"name": "Second", "start_odometer_km": 0, "archived": True}
        self.assertEqual(self.alex.put(f"{self.base}/cars/{second['id']}", json=body).status_code, 200)
        body["archived"] = False
        self.assertEqual(code(self.alex.put(f"{self.base}/cars/{second['id']}", json=body), 409), "limit_reached")

    def test_members_follow_the_plan(self):
        self.assertEqual(self.alex.post(f"{self.base}/members", json={"display_name": "Gran"}).status_code, 201)
        response = self.alex.post(f"{self.base}/members", json={"display_name": "Kid"})
        self.assertEqual(response.json()["detail"]["params"]["limit"], "members_per_group")
        self.set_plan("plus")
        self.assertEqual(self.alex.post(f"{self.base}/members", json={"display_name": "Kid"}).status_code, 201)

    def test_unknown_plan(self):
        response = self.root.put(f"/v1/admin/groups/{self.gid}/plan", json={"plan": "gold"})
        self.assertEqual(code(response, 422), "plan_unknown")

    def test_default_plan_clears_until(self):
        group = self.set_plan(None, until=FUTURE, note="  ")
        self.assertEqual((group["plan"], group["plan_until"], group["plan_note"]), (None, None, None))

    def test_admin_list(self):
        self.set_plan("plus", until=FUTURE, note="Invoice 2026-001")
        groups = self.root.get("/v1/admin/groups").json()
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(
            (group["name"], group["plan"], group["plan_until"], group["plan_note"], group["effective_plan"]),
            ("Test group", "plus", FUTURE, "Invoice 2026-001", "plus"),
        )
        self.assertEqual(group["usage"], {"members_per_group": 2, "cars_per_group": 1, "receipt_mb_per_group": 0.0})
        self.assertEqual(group["admins"], [{"user_id": self.alex_id, "display_name": "Alex"}])
        self.assertIsNotNone(group["last_activity_at"])
        # Nothing about entries or amounts
        self.assertEqual(set(group), {
            "id", "name", "created_at", "last_activity_at", "plan", "plan_until", "plan_note",
            "effective_plan", "usage", "admins",
        })  # fmt: skip

    def test_admin_only(self):
        # sam is a member of the group, not an admin of the instance
        self.assertEqual(code(self.sam.get("/v1/admin/groups"), 403), "instance_admin_only")
        self.assertEqual(code(self.sam.put(f"/v1/admin/groups/{self.gid}/plan", json={}), 403), "instance_admin_only")
        self.assertEqual(code(self.root.put("/v1/admin/groups/999/plan", json={}), 404), "group_not_found")

    def test_export_leaves_the_plan_behind(self):
        self.set_plan("plus", until=FUTURE, note="Invoice 2026-001")
        export = self.alex.get(f"{self.base}/export.json").json()
        self.assertFalse({"plan", "plan_until", "plan_note"} & set(export["group"]))
        self.assertNotIn("Invoice", json.dumps(export))

    def test_import_has_to_fit_the_default_plan(self):
        self.set_plan("plus")
        self.add_car()
        export = self.alex.get(f"{self.base}/export.json").content
        member = f"/v1/groups/import?member={self.alex_id}"
        response = self.alex.post(member, content=export, headers={"Content-Type": "application/json"})
        self.assertEqual(response.json()["detail"]["params"], {"limit": "cars_per_group", "max": 1, "plan": "free"})
        self.file.write({**PLANS, "default": "plus"})
        response = self.alex.post(member, content=export, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["plan"]["id"], "plus")


class BillingLinkTests(HostingTestCase):
    env_values = {"BILLING_URL": "https://billing.example.org/fahrma", "OPERATOR_TOKEN": "", "OPERATOR_TOKEN_FILE": ""}

    def test_without_billing_url(self):
        with mock.patch.dict(os.environ, {"BILLING_URL": ""}):
            self.assertEqual(code(self.alex.post(f"{self.base}/billing-link"), 404), "billing_disabled")

    def test_group_admins_only(self):
        self.assertTrue(self.env.client(None).get("/v1/meta").json()["billing"])
        self.assertEqual(code(self.sam.post(f"{self.base}/billing-link"), 403), "admin_only")

    def test_link_without_operator_token(self):
        url = self.alex.post(f"{self.base}/billing-link").json()["url"]
        self.assertEqual(url, f"https://billing.example.org/fahrma#group={self.gid}&plan=free")


class OperatorTestCase(HostingTestCase):
    env_values = {"BILLING_URL": "https://billing.example.org/fahrma", "OPERATOR_TOKEN": TOKEN}

    def setUp(self):
        super().setUp()
        # Like a billing service: no login, no CSRF header, no Origin
        self.operator = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})

    def billing_token(self) -> str:
        url = self.alex.post(f"{self.base}/billing-link").json()["url"]
        fragment = dict(part.split("=", 1) for part in url.split("#", 1)[1].split("&"))
        self.assertEqual((fragment["group"], fragment["plan"]), (str(self.gid), "free"))
        return fragment["token"]

    def verify(self, token):
        return self.operator.post("/v1/operator/billing-link/verify", json={"token": token})


class OperatorApiTests(OperatorTestCase):
    def test_off_without_token(self):
        with mock.patch.dict(os.environ, {"OPERATOR_TOKEN": ""}):
            self.assertEqual(code(self.operator.get("/v1/operator/groups"), 404), "operator_api_disabled")

    def test_needs_the_token(self):
        for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": f"Basic {TOKEN}"}):
            with self.subTest(headers=headers):
                client = TestClient(app, headers=headers)
                self.assertEqual(code(client.get("/v1/operator/groups"), 401), "operator_unauthorized")
        # A login is no substitute, not even an instance admin's
        self.assertEqual(code(self.root.get("/v1/operator/groups"), 401), "operator_unauthorized")

    def test_set_and_read_plan(self):
        response = self.operator.put(
            f"/v1/operator/groups/{self.gid}/plan", json={"plan": "plus", "until": FUTURE, "note": "Order 42"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["effective_plan"], response.json()["plan_note"]), ("plus", "Order 42"))
        self.assertEqual(self.operator.get(f"/v1/operator/groups/{self.gid}").json()["plan_until"], FUTURE)
        self.assertEqual(self.alex.get(self.base).json()["plan"]["id"], "plus")
        self.assertEqual(self.add_car().status_code, 201)

    def test_list_and_filter(self):
        other = self.alex.post("/v1/groups", json={"name": "Other"}).json()["id"]
        self.operator.put(f"/v1/operator/groups/{other}/plan", json={"plan": "plus"})
        self.assertEqual([g["id"] for g in self.operator.get("/v1/operator/groups").json()], [self.gid, other])
        self.assertEqual([g["id"] for g in self.operator.get("/v1/operator/groups?plan=plus").json()], [other])

    def test_not_found(self):
        self.assertEqual(code(self.operator.get("/v1/operator/groups/999"), 404), "group_not_found")
        response = self.operator.put("/v1/operator/groups/999/plan", json={"plan": "plus"})
        self.assertEqual(code(response, 404), "group_not_found")

    def test_csrf_still_applies_elsewhere(self):
        response = self.operator.post("/v1/groups", json={"name": "No"})
        self.assertEqual(code(response, 403), "csrf_rejected")


class BillingTokenTests(OperatorTestCase):
    def test_verify(self):
        self.env.client(None)
        db = self.env.SessionLocal()
        try:
            db.get(User, self.alex_id).email = "alex@example.org"
            db.commit()
        finally:
            db.close()
        response = self.verify(self.billing_token())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual((data["group"]["id"], data["group"]["effective_plan"]), (self.gid, "free"))
        self.assertEqual(
            data["user"], {"user_id": self.alex_id, "display_name": "Alex", "email": "alex@example.org", "locale": None}
        )
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        self.assertLess(abs(expires - datetime.now(UTC) - timedelta(hours=1)), timedelta(minutes=1))

    def test_tampered_tokens(self):
        token = self.billing_token()
        payload, signature = token.split(".")
        other_payload = billing_link._b64(json.dumps({"v": 1, "g": self.gid, "u": self.sam_id, "p": "free",
                                                      "exp": 9999999999}).encode())  # fmt: skip
        for bad in ("", "x", token + "x", f"{other_payload}.{signature}", f"{payload}.", f".{signature}"):
            with self.subTest(token=bad):
                response = self.verify(bad)
                self.assertIn(response.status_code, (400, 422))
                if response.status_code == 400:
                    self.assertEqual(response.json()["detail"]["code"], "billing_token_invalid")

    def test_signed_with_another_key(self):
        db = self.env.SessionLocal()
        try:
            group, user = db.get(Group, self.gid), db.get(User, self.alex_id)
            forged = billing_link.create_token(group, user, "free", datetime.now(UTC), "f" * 40)
        finally:
            db.close()
        self.assertEqual(code(self.verify(forged), 400), "billing_token_invalid")

    def test_expired(self):
        db = self.env.SessionLocal()
        try:
            group, user = db.get(Group, self.gid), db.get(User, self.alex_id)
            old = billing_link.create_token(group, user, "free", datetime.now(UTC) - timedelta(hours=2), TOKEN)
        finally:
            db.close()
        self.assertEqual(code(self.verify(old), 400), "billing_token_invalid")

    def test_no_longer_admin(self):
        token = self.billing_token()
        self.alex.patch(f"{self.base}/members/{self.sam_id}", json={"role": "admin"})
        self.alex.patch(f"{self.base}/members/{self.alex_id}", json={"role": "member"})
        self.assertEqual(code(self.verify(token), 409), "billing_not_admin")

    def test_group_deleted(self):
        token = self.billing_token()
        self.alex.request("DELETE", self.base, json={"name": "Test group"})
        self.assertEqual(code(self.verify(token), 409), "billing_not_admin")

    def test_token_is_not_the_operator_token(self):
        token = self.billing_token()
        self.assertNotIn(TOKEN, token)
        client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(code(client.get("/v1/operator/groups"), 401), "operator_unauthorized")


class JoiningTests(HostingTestCase):
    def test_invitation_respects_the_plan(self):
        self.alex.post(f"{self.base}/members", json={"display_name": "Gran"})
        invite = self.alex.post(f"{self.base}/invites").json()
        response = accept(self.env.client(None), invite["url"], username="kim", password=PASSWORD)
        self.assertEqual(response.json()["detail"]["params"]["plan"], "free")
        self.set_plan("plus")
        response = accept(self.env.client(None), invite["url"], username="kim", password=PASSWORD)
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()

"""Accounts: registration, password, devices, instance admin, deletion, limits, exports."""

import json
import unittest
from unittest import mock

from app.models.settlement import Settlement
from app.models.trip import Trip
from tests.support import PASSWORD, ApiTestEnvironment, accept, token_of
from tests.test_api import GroupSetupMixin

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


def code(response, status_code: int) -> str:
    assert response.status_code == status_code, f"{response.status_code} != {status_code}: {response.text}"
    return response.json()["detail"]["code"]


class MetaAndRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()

    def tearDown(self):
        self.env.close()

    def register(self, **fields):
        body = {"username": "kim", "password": PASSWORD, **fields}
        return self.env.client(None).post("/v1/auth/register", json=body)

    def test_meta_defaults(self):
        meta = self.env.client(None).get("/v1/meta").json()
        self.assertEqual(meta["registration"], "invite")
        self.assertTrue(meta["setup_needed"])
        self.assertEqual(meta["links"], {"imprint_url": None, "privacy_url": None, "terms_url": None})
        self.assertEqual(set(meta["limits"].values()), {None})

    def test_meta_shows_operator_links_and_limits(self):
        env = {"IMPRINT_URL": "https://example.org/imprint", "MAX_CARS_PER_GROUP": "3"}
        with mock.patch.dict("os.environ", env):
            meta = self.env.client(None).get("/v1/meta").json()
        self.assertEqual(meta["links"]["imprint_url"], "https://example.org/imprint")
        self.assertEqual(meta["limits"]["cars_per_group"], 3)

    def test_registration_closed_by_default(self):
        self.env.create_user("alex", role="admin")
        self.assertEqual(code(self.register(), 403), "registration_closed")

    def test_open_registration(self):
        self.env.create_user("alex", role="admin")
        with mock.patch.dict("os.environ", {"REGISTRATION": "open"}):
            response = self.register(display_name="Kim", locale="en")
            self.assertEqual(response.status_code, 201, response.text)
            me = response.json()
            self.assertEqual((me["username"], me["role"], me["locale"], me["groups"]), ("kim", "user", "en", []))
            self.assertEqual(code(self.register(), 409), "username_taken")
            self.assertEqual(code(self.register(username="K"), 422), "username_invalid")

    def test_open_registration_needs_setup_first(self):
        with mock.patch.dict("os.environ", {"REGISTRATION": "open"}):
            self.assertEqual(code(self.register(), 409), "setup_required")

    def test_open_registration_with_terms(self):
        self.env.create_user("alex", role="admin")
        with mock.patch.dict("os.environ", {"REGISTRATION": "open", "TERMS_URL": "https://example.org/terms"}):
            self.assertEqual(code(self.register(), 422), "terms_not_accepted")
            self.assertEqual(self.register(accept_terms=True).status_code, 201)

    def test_registration_is_rate_limited(self):
        self.env.create_user("alex", role="admin")
        with mock.patch.dict("os.environ", {"REGISTRATION": "open"}):
            for i in range(5):
                self.assertEqual(self.register(username=f"kim{i}").status_code, 201)
            self.assertEqual(code(self.register(username="kim9"), 429), "too_many_attempts")


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()
        self.env.create_user("alex", role="admin")
        self.phone = self.env.client(None)
        self.phone.headers["User-Agent"] = IPHONE
        self.phone.post("/v1/auth/login", json={"username": "alex", "password": PASSWORD})
        self.laptop = self.env.client(None)
        self.laptop.headers["User-Agent"] = FIREFOX
        self.laptop.post("/v1/auth/login", json={"username": "alex", "password": PASSWORD})

    def tearDown(self):
        self.env.close()

    def test_device_list(self):
        sessions = self.phone.get("/v1/account/sessions").json()
        self.assertEqual(
            sorted((s["device"], s["current"]) for s in sessions),
            [("Linux · Firefox", False), ("iPhone · Safari", True)],
        )

    def test_revoke_other_device(self):
        laptop_id = next(s["id"] for s in self.phone.get("/v1/account/sessions").json() if not s["current"])
        self.assertEqual(self.phone.delete(f"/v1/account/sessions/{laptop_id}").status_code, 204)
        self.assertEqual(self.laptop.get("/v1/auth/me").status_code, 401)
        self.assertEqual(self.phone.get("/v1/auth/me").status_code, 200)

    def test_revoke_all_others(self):
        self.assertEqual(self.phone.post("/v1/account/sessions/revoke-others").status_code, 204)
        self.assertEqual(self.laptop.get("/v1/auth/me").status_code, 401)
        self.assertEqual(len(self.phone.get("/v1/account/sessions").json()), 1)

    def test_change_password(self):
        new = "ein-neues-passwort-456"
        wrong = self.phone.post("/v1/account/password", json={"current_password": "nope", "new_password": new})
        self.assertEqual(code(wrong, 403), "wrong_password")
        short = self.phone.post("/v1/account/password", json={"current_password": PASSWORD, "new_password": "x"})
        self.assertEqual(code(short, 422), "password_too_short")
        ok = self.phone.post("/v1/account/password", json={"current_password": PASSWORD, "new_password": new})
        self.assertEqual(ok.status_code, 204)
        # This device stays logged in, all others are logged out
        self.assertEqual(self.phone.get("/v1/auth/me").status_code, 200)
        self.assertEqual(self.laptop.get("/v1/auth/me").status_code, 401)
        self.assertEqual(self.env.client("alex", password=new).get("/v1/auth/me").status_code, 200)

    def test_my_data_export(self):
        gid = self.phone.post("/v1/groups", json={"name": "Test group"}).json()["id"]
        data = self.phone.get("/v1/account/export.json")
        self.assertIn("attachment", data.headers["Content-Disposition"])
        body = data.json()
        self.assertEqual(body["format"], "fahrma-account/1")
        self.assertEqual(body["account"]["username"], "alex")
        self.assertNotIn("password_hash", json.dumps(body))
        self.assertEqual([g["id"] for g in body["groups"]], [gid])
        self.assertEqual(len(body["sessions"]), 2)


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()
        self.env.create_user("alex", role="admin")
        self.env.create_user("sam")
        self.alex = self.env.client("alex")
        self.sam = self.env.client("sam")
        users = self.alex.get("/v1/admin/users").json()
        self.ids = {user["username"]: user["id"] for user in users}

    def tearDown(self):
        self.env.close()

    def test_only_admins(self):
        self.assertEqual(code(self.sam.get("/v1/admin/users"), 403), "instance_admin_only")
        self.assertEqual(code(self.sam.post("/v1/admin/invitations", json={}), 403), "instance_admin_only")

    def test_account_list_has_no_content(self):
        self.alex.post("/v1/groups", json={"name": "Secret group"})
        users = self.alex.get("/v1/admin/users").json()
        alex = next(user for user in users if user["username"] == "alex")
        self.assertEqual(alex["group_count"], 1)
        self.assertNotIn("Secret group", json.dumps(users))

    def test_deactivate_logs_out_everywhere(self):
        response = self.alex.patch(f"/v1/admin/users/{self.ids['sam']}", json={"is_active": False})
        self.assertFalse(response.json()["is_active"])
        self.assertEqual(self.sam.get("/v1/auth/me").status_code, 401)
        login = self.env.client(None).post("/v1/auth/login", json={"username": "sam", "password": PASSWORD})
        self.assertEqual(login.status_code, 401)
        self.alex.patch(f"/v1/admin/users/{self.ids['sam']}", json={"is_active": True})
        self.assertEqual(self.env.client("sam").get("/v1/auth/me").status_code, 200)

    def test_last_admin_is_protected(self):
        alex = f"/v1/admin/users/{self.ids['alex']}"
        self.assertEqual(code(self.alex.patch(alex, json={"role": "user"}), 409), "last_instance_admin")
        self.assertEqual(code(self.alex.patch(alex, json={"is_active": False}), 409), "self_deactivate")
        self.assertEqual(code(self.alex.delete(alex), 409), "self_delete")
        self.alex.patch(f"/v1/admin/users/{self.ids['sam']}", json={"role": "admin"})
        self.assertEqual(self.alex.patch(alex, json={"role": "user"}).json()["role"], "user")

    def test_password_reset_link(self):
        link = self.alex.post(f"/v1/admin/users/{self.ids['sam']}/password-reset").json()
        anonymous = self.env.client(None)
        info = anonymous.post("/v1/invites/inspect", json={"token": token_of(link["url"])}).json()
        self.assertEqual((info["kind"], info["username"]), ("password_reset", "sam"))
        new = "ein-neues-passwort-456"
        self.assertEqual(accept(anonymous, link["url"], password=new).json()["kind"], "password_reset")
        self.assertEqual(anonymous.get("/v1/auth/me").json()["username"], "sam")
        # The old session is gone, the link is used up
        self.assertEqual(self.sam.get("/v1/auth/me").status_code, 401)
        self.assertEqual(code(accept(self.env.client(None), link["url"], password=new), 404), "invite_invalid")

    def test_signup_invitation(self):
        link = self.alex.post("/v1/admin/invitations", json={"role": "admin", "note": "for Kim"}).json()
        listed = self.alex.get("/v1/admin/invitations").json()
        self.assertEqual([(i["note"], i["role"]) for i in listed], [("for Kim", "admin")])
        client = self.env.client(None)
        response = accept(client, link["url"], username="kim", display_name="Kim", password=PASSWORD)
        self.assertEqual(response.json(), {"kind": "signup", "group_id": None})
        self.assertEqual(client.get("/v1/auth/me").json()["role"], "admin")
        self.assertEqual(self.alex.get("/v1/admin/invitations").json(), [])

    def test_revoke_invitation(self):
        link = self.alex.post("/v1/admin/invitations", json={}).json()
        self.assertEqual(self.alex.delete(f"/v1/admin/invitations/{link['id']}").status_code, 204)
        response = accept(self.env.client(None), link["url"], username="kim", password=PASSWORD)
        self.assertEqual(code(response, 404), "invite_invalid")

    def test_wrong_tokens_are_rate_limited(self):
        client = self.env.client(None)
        for _ in range(20):
            client.post("/v1/invites/inspect", json={"token": "wrong-token-wrong-token"})
        self.assertEqual(code(client.post("/v1/invites/inspect", json={"token": "x" * 20}), 429), "too_many_attempts")


class GroupInvitationTests(GroupSetupMixin, unittest.TestCase):
    def test_logged_in_account_joins(self):
        self.env.create_user("kim")
        kim = self.env.client("kim")
        invite = self.alex.post(f"{self.base}/invites").json()
        self.assertEqual(accept(kim, invite["url"]).json(), {"kind": "group", "group_id": self.gid})
        self.assertEqual([g["id"] for g in kim.get("/v1/auth/me").json()["groups"]], [self.gid])

    def test_member_does_not_use_up_the_link(self):
        invite = self.alex.post(f"{self.base}/invites").json()
        self.assertEqual(accept(self.sam, invite["url"]).status_code, 200)
        response = accept(self.env.client(None), invite["url"], username="kim", password=PASSWORD)
        self.assertEqual(response.status_code, 200)


class DeletionTests(GroupSetupMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)], day="2026-11-02")
        self.trip(self.sam, 10100, 10300, [(self.sam_id, 1)], day="2026-11-03")
        self.fuel(self.sam, 3000, self.sam_id, day="2026-11-04")
        settled = self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-20"})
        self.assertEqual(settled.status_code, 201, settled.text)
        self.settlement_id = settled.json()["id"]
        self.trip(self.sam, 10300, 10400, [(self.sam_id, 1)], day="2026-11-21")

    def delete_sam(self):
        response = self.sam.request("DELETE", "/v1/account", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 204, response.text)

    def test_wrong_password(self):
        response = self.sam.request("DELETE", "/v1/account", json={"password": "wrong-password"})
        self.assertEqual(code(response, 403), "wrong_password")

    def test_balances_stay_and_name_disappears(self):
        balance = self.alex.get(f"{self.base}/balance").json()
        settlement = self.alex.get(f"{self.base}/settlements/{self.settlement_id}").json()
        self.delete_sam()
        anonymous = f"Person {self.sam_id}"
        after = self.alex.get(f"{self.base}/balance").json()
        self.assertEqual(
            [(m["user_id"], m["balance_cents"]) for m in after["members"]],
            [(m["user_id"], m["balance_cents"]) for m in balance["members"]],
        )
        frozen = self.alex.get(f"{self.base}/settlements/{self.settlement_id}").json()
        self.assertEqual(frozen["transfers"], settlement["transfers"])
        names = {m["user_id"]: m["display_name"] for m in frozen["result"]["members"]}
        self.assertEqual(names[self.sam_id], anonymous)
        db = self.env.SessionLocal()
        try:
            snapshot = db.get(Settlement, self.settlement_id).snapshot_json
            self.assertNotIn("Sam", snapshot)
        finally:
            db.close()
        member = next(m for m in self.alex.get(self.base).json()["members"] if m["user_id"] == self.sam_id)
        self.assertEqual((member["display_name"], member["active"], member["deleted"]), (anonymous, False, True))
        self.assertNotIn("sam", member["username"])
        # Login is gone; the name is free again
        login = self.env.client(None).post("/v1/auth/login", json={"username": "sam", "password": PASSWORD})
        self.assertEqual(login.status_code, 401)
        self.env.create_user("sam")

    def test_deleted_member_cannot_be_reactivated(self):
        self.delete_sam()
        response = self.alex.patch(f"{self.base}/members/{self.sam_id}", json={"active": True})
        self.assertEqual(code(response, 409), "member_deleted")

    def test_last_group_admin_hands_over(self):
        # sam becomes instance admin so alex may delete the account
        self.alex.patch(f"/v1/admin/users/{self.sam_id}", json={"role": "admin"})
        preview = self.alex.get("/v1/account/deletion-preview").json()
        self.assertEqual(preview["groups_deleted"], [])
        self.assertEqual(preview["admin_handover"], [{"group_id": self.gid, "group_name": "Test group",
                                                      "new_admin_name": "Sam"}])  # fmt: skip
        response = self.alex.request("DELETE", "/v1/account", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.sam.get(self.base).json()["my_role"], "admin")

    def test_last_instance_admin_cannot_delete_itself(self):
        response = self.alex.request("DELETE", "/v1/account", json={"password": PASSWORD})
        self.assertEqual(code(response, 409), "last_instance_admin")

    def test_group_without_other_members_is_deleted(self):
        solo = self.sam.post("/v1/groups", json={"name": "Solo"}).json()["id"]
        preview = self.sam.get("/v1/account/deletion-preview").json()
        self.assertEqual(preview["groups_deleted"], [{"id": solo, "name": "Solo"}])
        self.assertEqual(preview["groups_kept"], [{"id": self.gid, "name": "Test group"}])
        self.delete_sam()
        self.env.create_user("kim", role="admin")
        db = self.env.SessionLocal()
        try:
            self.assertEqual(db.query(Trip).filter(Trip.group_id == self.gid).count(), 3)
        finally:
            db.close()
        self.assertEqual(self.alex.get(f"/v1/groups/{solo}").status_code, 404)

    def test_admin_deletes_account(self):
        self.assertEqual(self.alex.delete(f"/v1/admin/users/{self.sam_id}").status_code, 204)
        self.assertEqual(self.sam.get("/v1/auth/me").status_code, 401)
        self.assertNotIn(self.sam_id, [u["id"] for u in self.alex.get("/v1/admin/users").json()])


class GroupDeleteAndExportTests(GroupSetupMixin, unittest.TestCase):
    def test_export(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1), (self.sam_id, 1)])
        response = self.sam.get(f"{self.base}/export.json")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        data = response.json()
        self.assertEqual(data["format"], "fahrma-group/1")
        self.assertEqual(data["group"]["name"], "Test group")
        self.assertEqual(len(data["trips"]), 1)
        self.assertEqual(len(data["trip_shares"]), 2)
        self.assertEqual({m["display_name"] for m in data["members"]}, {"Alex", "Sam"})
        self.assertNotIn("password", json.dumps(data))

    def test_delete_group(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        self.fuel(self.alex, 1000, self.alex_id)
        self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-20"})
        self.assertEqual(code(self.sam.request("DELETE", self.base, json={"name": "Test group"}), 403), "admin_only")
        self.assertEqual(
            code(self.alex.request("DELETE", self.base, json={"name": "Wrong"}), 422), "group_name_mismatch"
        )
        self.assertEqual(self.alex.request("DELETE", self.base, json={"name": "Test group"}).status_code, 204)
        self.assertEqual(self.alex.get(self.base).status_code, 404)
        db = self.env.SessionLocal()
        try:
            self.assertEqual(db.query(Trip).count(), 0)
        finally:
            db.close()


class LimitTests(GroupSetupMixin, unittest.TestCase):
    def test_cars_per_group(self):
        with mock.patch.dict("os.environ", {"MAX_CARS_PER_GROUP": "1"}):
            second = self.alex.post(f"{self.base}/cars", json={"name": "Second", "start_odometer_km": 0})
            detail = second.json()["detail"]
            self.assertEqual((second.status_code, detail["code"]), (409, "limit_reached"))
            self.assertEqual(detail["params"], {"limit": "cars_per_group", "max": 1})
            self.alex.put(
                f"{self.base}/cars/{self.car_id}",
                json={"name": "Test car", "start_odometer_km": 10000, "archived": True},
            )
            third = self.alex.post(f"{self.base}/cars", json={"name": "Second", "start_odometer_km": 0})
            self.assertEqual(third.status_code, 201)

    def test_members_per_group(self):
        invite = self.alex.post(f"{self.base}/invites").json()
        with mock.patch.dict("os.environ", {"MAX_MEMBERS_PER_GROUP": "2"}):
            response = accept(self.env.client(None), invite["url"], username="kim", password=PASSWORD)
        self.assertEqual(code(response, 409), "limit_reached")
        # The link was not used up
        response = accept(self.env.client(None), invite["url"], username="kim", password=PASSWORD)
        self.assertEqual(response.status_code, 200)

    def test_groups_per_user(self):
        with mock.patch.dict("os.environ", {"MAX_GROUPS_PER_USER": "1"}):
            self.assertEqual(code(self.alex.post("/v1/groups", json={"name": "Second"}), 409), "limit_reached")


if __name__ == "__main__":
    unittest.main()

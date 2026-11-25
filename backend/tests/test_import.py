"""Group import: export → import keeps every number; placeholders and personal links."""

import json
import unittest
from unittest import mock

from app.models.user import User
from app.services import group_import
from tests.support import PASSWORD, accept, token_of
from tests.test_accounts import code
from tests.test_api import GroupSetupMixin


def by_name(rows: list[dict], key: str = "balance_cents") -> dict[str, int]:
    return {row["display_name"]: row[key] for row in rows}


class RichGroupMixin(GroupSetupMixin):
    """alex, sam and kim (deleted later) with trips, fuel, expenses and a settlement with a paid transfer."""

    def setUp(self):
        super().setUp()
        invite = self.alex.post(f"{self.base}/invites").json()
        self.kim = self.env.client(None)
        accept(self.kim, invite["url"], username="kim", display_name="Kim", password=PASSWORD)
        self.kim_id = self.kim.get("/v1/auth/me").json()["id"]
        a, s, k = self.alex_id, self.sam_id, self.kim_id
        self.trip(self.alex, 10000, 10100, [(a, 1)])
        second = self.trip(
            self.sam,
            10100,
            10300,
            [(s, 1), (a, 1)],
            external=[{"payer_name": "Passenger", "amount_cents": 500, "received_by_user_id": s}],
        )
        self.trip(self.kim, 10300, 10400, [(k, 1)])
        self.fuel(self.alex, 6000, a)
        self.fuel(self.sam, 3000, s)
        self.expense(self.alex, 1200, a, "single", allocated_user_id=s)
        self.expense(self.sam, 800, s, "trip", trip_id=second["id"])
        self.expense(self.kim, 900, k, "equal")
        settlement = self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-20"})
        self.assertEqual(settlement.status_code, 201, settlement.text)
        self.settlement = settlement.json()
        paid = self.alex.post(f"{self.base}/transfers/{self.settlement['transfers'][0]['id']}/paid")
        self.assertEqual(paid.status_code, 200, paid.text)
        self.trip(self.alex, 10400, 10500, [(a, 1)], day="2026-11-22")
        self.fuel(self.sam, 2500, s, day="2026-11-22")
        self.assertEqual(self.kim.request("DELETE", "/v1/account", json={"password": PASSWORD}).status_code, 204)
        self.export = self.alex.get(f"{self.base}/export.json").json()

    def expense(self, client, cents, payer, allocation, **fields):
        response = client.post(
            f"{self.base}/expenses",
            json={
                "date": "2026-11-12",
                "category": "other",
                "amount_cents": cents,
                "paid_by_user_id": payer,
                "allocation": allocation,
                **fields,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def raw(self, data: dict | None = None) -> bytes:
        return json.dumps(data if data is not None else self.export).encode()

    def do_import(self, client=None, member=None, data=None):
        client = client or self.alex
        member = self.alex_id if member is None else member
        return client.post(
            f"/v1/groups/import?member={member}", content=self.raw(data), headers={"Content-Type": "application/json"}
        )

    def imported(self) -> tuple[int, dict]:
        response = self.do_import()
        self.assertEqual(response.status_code, 201, response.text)
        group = response.json()
        return group["id"], group


class ImportTests(RichGroupMixin, unittest.TestCase):
    def test_preview(self):
        response = self.alex.post("/v1/groups/import/check", content=self.raw())
        self.assertEqual(response.status_code, 200, response.text)
        preview = response.json()
        self.assertEqual((preview["name"], preview["currency"]), ("Test group", "EUR"))
        self.assertEqual(preview["counts"], {"cars": 1, "trips": 4, "fuel": 3, "expenses": 3, "settlements": 1})
        self.assertEqual((preview["first_date"], preview["last_date"]), ("2026-11-10", "2026-11-22"))
        members = {m["user_id"]: (m["display_name"], m["role"], m["active"], m["deleted"]) for m in preview["members"]}
        self.assertEqual(members[self.alex_id], ("Alex", "admin", True, False))
        self.assertEqual(members[self.kim_id], (f"Person {self.kim_id}", "member", False, True))
        # Nothing was stored
        self.assertEqual(len(self.alex.get("/v1/auth/me").json()["groups"]), 1)

    def test_round_trip_keeps_every_number(self):
        new_gid, group = self.imported()
        new_base = f"/v1/groups/{new_gid}"
        self.assertNotEqual(new_gid, self.gid)
        self.assertEqual(group["my_role"], "admin")
        members = {m["display_name"]: m for m in group["members"]}
        self.assertEqual(members["Alex"]["user_id"], self.alex_id)
        self.assertTrue(members["Sam"]["placeholder"])
        self.assertNotEqual(members["Sam"]["user_id"], self.sam_id)
        deleted = [m for m in group["members"] if m["deleted"]]
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0]["display_name"], f"Person {deleted[0]['user_id']}")

        old_balance = self.alex.get(f"{self.base}/balance").json()
        new_balance = self.alex.get(f"{new_base}/balance").json()
        self.assertEqual(by_name(new_balance["members"]), by_name(old_balance["members"]))
        self.assertEqual(new_balance["total_cost_cents"], old_balance["total_cost_cents"])

        old_list = self.alex.get(f"{self.base}/settlements").json()
        new_list = self.alex.get(f"{new_base}/settlements").json()
        self.assertEqual(
            [(s["period_end"], s["total_cost_cents"], s["open_transfers"]) for s in new_list],
            [(s["period_end"], s["total_cost_cents"], s["open_transfers"]) for s in old_list],
        )
        old = self.alex.get(f"{self.base}/settlements/{old_list[0]['id']}").json()
        new = self.alex.get(f"{new_base}/settlements/{new_list[0]['id']}").json()
        old_names = {m["user_id"]: m["display_name"] for m in old["result"]["members"]}
        new_names = {m["user_id"]: m["display_name"] for m in new["result"]["members"]}
        self.assertEqual(by_name(new["result"]["members"]), by_name(old["result"]["members"]))
        self.assertEqual(
            sorted((new_names[t["from_user_id"]], new_names[t["to_user_id"]], t["amount_cents"], bool(t["paid_at"]))
                   for t in new["transfers"]),
            sorted((old_names[t["from_user_id"]], old_names[t["to_user_id"]], t["amount_cents"], bool(t["paid_at"]))
                   for t in old["transfers"]),
        )  # fmt: skip
        # Every ID in the snapshot belongs to the new group
        new_member_ids = {m["user_id"] for m in group["members"]}
        self.assertLessEqual(set(new_names), new_member_ids)
        new_car = self.alex.get(f"{new_base}/cars").json()[0]
        self.assertEqual({c["car_id"] for c in new["result"]["cars"]}, {new_car["id"]})

        old_trips = self.alex.get(f"{self.base}/trips").json()
        new_trips = self.alex.get(f"{new_base}/trips").json()
        self.assertEqual(
            sorted((t["start_km"], t["end_km"], t["cost_cents"], t["settlement_id"] is None) for t in new_trips),
            sorted((t["start_km"], t["end_km"], t["cost_cents"], t["settlement_id"] is None) for t in old_trips),
        )
        expenses = self.alex.get(f"{new_base}/expenses").json()
        linked = next(e for e in expenses if e["allocation"] == "trip")
        self.assertIn(linked["trip_id"], {t["id"] for t in new_trips})
        audit = self.alex.get(f"{new_base}/audit").json()
        self.assertEqual((audit[0]["entity"], audit[0]["action"]), ("group", "import"))
        self.assertGreater(len(audit), 10)

    def test_imported_group_keeps_working(self):
        new_gid, group = self.imported()
        new_base = f"/v1/groups/{new_gid}"
        sam = next(m["user_id"] for m in group["members"] if m["display_name"] == "Sam")
        car = self.alex.get(f"{new_base}/cars").json()[0]["id"]
        trip = self.alex.post(
            f"{new_base}/trips",
            json={"car_id": car, "date": "2026-11-23", "start_km": 10500, "end_km": 10600,
                  "shares": [{"user_id": sam, "weight": 1}], "external": []},
        )  # fmt: skip
        self.assertEqual(trip.status_code, 201, trip.text)
        overlap = self.alex.post(
            f"{new_base}/trips",
            json={"car_id": car, "date": "2026-11-23", "start_km": 10450, "end_km": 10460,
                  "shares": [{"user_id": sam, "weight": 1}], "external": []},
        )  # fmt: skip
        self.assertEqual(code(overlap, 409), "trip_overlap")
        settlement = self.alex.post(f"{new_base}/settlements", json={"period_end": "2026-11-23"})
        self.assertEqual(settlement.status_code, 201, settlement.text)

    def test_member_must_be_active_and_in_the_file(self):
        self.assertEqual(code(self.do_import(member=self.kim_id), 422), "import_member_invalid")
        self.assertEqual(code(self.do_import(member=99999), 422), "import_member_invalid")

    def test_rejects_other_files(self):
        response = self.alex.post("/v1/groups/import/check", content=b"not json")
        self.assertEqual(code(response, 422), "import_invalid")
        response = self.alex.post("/v1/groups/import/check", content=self.raw({"format": "fahrma-account/1"}))
        self.assertEqual(code(response, 422), "import_format")
        self.assertEqual(response.json()["detail"]["params"]["found"], "fahrma-account/1")

    def test_rejects_foreign_references(self):
        for change, where in (
            (lambda d: d["trips"][0].update(car_id=999), "trips[0].car_id"),
            (lambda d: d["fuel"][0].update(paid_by_user_id=999), "fuel[0].paid_by_user_id"),
            (lambda d: d["expenses"][1].update(trip_id=999), "expenses[1].trip_id"),
            (lambda d: d["settlements"][0]["snapshot"]["members"][0].update(user_id=999), "settlements[0].snapshot"),
            (lambda d: d["trip_shares"].append(dict(d["trip_shares"][0])), "trip_shares["),
            (lambda d: d["trips"][0].update(amount_cents=1, start_km=-1), "trips.0.start_km"),
        ):
            data = json.loads(json.dumps(self.export))
            change(data)
            response = self.do_import(data=data)
            self.assertEqual(code(response, 422), "import_invalid", where)
            self.assertTrue(response.json()["detail"]["params"]["where"].startswith(where), response.text)
        self.assertEqual(len(self.alex.get("/v1/auth/me").json()["groups"]), 1)

    def test_too_large(self):
        with mock.patch.object(group_import, "MAX_IMPORT_BYTES", 1000):
            self.assertEqual(code(self.do_import(), 413), "import_too_large")

    def test_limits(self):
        with mock.patch.dict("os.environ", {"MAX_GROUPS_PER_USER": "1"}):
            self.assertEqual(code(self.do_import(), 409), "limit_reached")
        with mock.patch.dict("os.environ", {"MAX_MEMBERS_PER_GROUP": "1"}):
            self.assertEqual(code(self.do_import(), 409), "limit_reached")

    def test_unknown_time_zone_falls_back(self):
        data = json.loads(json.dumps(self.export))
        data["group"]["timezone"] = "Mars/Olympus"
        self.assertIsNone(self.do_import(data=data).json()["timezone"])

    def test_placeholders_are_not_accounts(self):
        self.imported()
        names = [u["username"] for u in self.alex.get("/v1/admin/users").json()]
        self.assertEqual(sorted(names), ["alex", "sam"])
        db = self.env.SessionLocal()
        try:
            placeholder = db.query(User).filter(User.placeholder.is_(True)).one()
            login = self.env.client(None).post(
                "/v1/auth/login", json={"username": placeholder.username, "password": "!"}
            )
            self.assertEqual(login.status_code, 401)
        finally:
            db.close()

    def test_deleting_the_group_removes_its_placeholders(self):
        new_gid, _group = self.imported()
        db = self.env.SessionLocal()
        try:
            before = db.query(User).count()
        finally:
            db.close()
        response = self.alex.request("DELETE", f"/v1/groups/{new_gid}", json={"name": "Test group"})
        self.assertEqual(response.status_code, 204, response.text)
        db = self.env.SessionLocal()
        try:
            self.assertEqual(db.query(User).count(), before - 2)
            self.assertEqual(db.query(User).filter(User.placeholder.is_(True)).count(), 0)
        finally:
            db.close()


class PersonalLinkTests(RichGroupMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.new_gid, group = self.imported()
        self.new_base = f"/v1/groups/{self.new_gid}"
        self.placeholder = next(m["user_id"] for m in group["members"] if m["display_name"] == "Sam")
        self.balance = by_name(self.alex.get(f"{self.new_base}/balance").json()["members"])

    def personal_link(self, user_id=None) -> dict:
        response = self.alex.post(f"{self.new_base}/members/{user_id or self.placeholder}/invite")
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_new_account_takes_over_the_place(self):
        link = self.personal_link()
        member = next(m for m in self.alex.get(self.new_base).json()["members"] if m["user_id"] == self.placeholder)
        self.assertEqual(member["link_expires_at"], link["expires_at"])
        info = self.env.client(None).post("/v1/invites/inspect", json={"token": token_of(link["url"])}).json()
        self.assertEqual((info["kind"], info["group_name"], info["member_name"]), ("group", "Test group", "Sam"))
        newcomer = self.env.client(None)
        response = accept(newcomer, link["url"], username="samuel", password=PASSWORD)
        self.assertEqual(response.json(), {"kind": "group", "group_id": self.new_gid})
        me = newcomer.get("/v1/auth/me").json()
        self.assertEqual((me["id"], me["username"], me["display_name"]), (self.placeholder, "samuel", "Sam"))
        self.assertEqual(by_name(newcomer.get(f"{self.new_base}/balance").json()["members"]), self.balance)
        member = next(m for m in self.alex.get(self.new_base).json()["members"] if m["user_id"] == self.placeholder)
        self.assertFalse(member["placeholder"])
        self.assertEqual(code(accept(self.env.client(None), link["url"], username="x" * 5, password=PASSWORD), 404),
                         "invite_invalid")  # fmt: skip

    def test_existing_account_takes_over_the_bookings(self):
        link = self.personal_link()
        self.env.create_user("samuel", display_name="Samuel")
        samuel = self.env.client("samuel")
        samuel_id = samuel.get("/v1/auth/me").json()["id"]
        response = accept(samuel, link["url"])
        self.assertEqual(response.status_code, 200, response.text)
        group = samuel.get(self.new_base).json()
        ids = {m["user_id"] for m in group["members"]}
        self.assertIn(samuel_id, ids)
        self.assertNotIn(self.placeholder, ids)
        balance = by_name(samuel.get(f"{self.new_base}/balance").json()["members"])
        expected = {("Samuel" if name == "Sam" else name): cents for name, cents in self.balance.items()}
        self.assertEqual(balance, expected)
        settlement = samuel.get(f"{self.new_base}/settlements").json()[0]
        detail = samuel.get(f"{self.new_base}/settlements/{settlement['id']}").json()
        self.assertIn(samuel_id, {m["user_id"] for m in detail["result"]["members"]})
        self.assertNotIn(self.placeholder, {m["user_id"] for m in detail["result"]["members"]})
        parties = {t["from_user_id"] for t in detail["transfers"]} | {t["to_user_id"] for t in detail["transfers"]}
        self.assertIn(samuel_id, parties)
        db = self.env.SessionLocal()
        try:
            self.assertIsNone(db.get(User, self.placeholder))
        finally:
            db.close()

    def test_member_of_the_group_cannot_use_it(self):
        link = self.personal_link()
        self.assertEqual(code(accept(self.alex, link["url"]), 409), "already_in_group")
        # Still usable by the right person
        self.assertEqual(accept(self.env.client(None), link["url"], username="samuel", password=PASSWORD).status_code,
                         200)  # fmt: skip

    def test_only_the_newest_link_works(self):
        first = self.personal_link()
        self.personal_link()
        response = accept(self.env.client(None), first["url"], username="samuel", password=PASSWORD)
        self.assertEqual(code(response, 404), "invite_invalid")

    def test_only_for_active_placeholders(self):
        self.assertEqual(
            code(self.alex.post(f"{self.new_base}/members/{self.alex_id}/invite"), 404), "member_not_found"
        )
        self.alex.patch(f"{self.new_base}/members/{self.placeholder}", json={"active": False})
        self.assertEqual(code(self.alex.post(f"{self.new_base}/members/{self.placeholder}/invite"), 409),
                         "member_inactive")  # fmt: skip


class PersonWithoutAccountTests(GroupSetupMixin, unittest.TestCase):
    def add(self, name="Grandma"):
        response = self.alex.post(f"{self.base}/members", json={"display_name": name})
        self.assertEqual(response.status_code, 201, response.text)
        return next(m for m in response.json()["members"] if m["display_name"] == name)

    def test_add_rename_and_book(self):
        person = self.add()
        self.assertTrue(person["placeholder"])
        self.assertEqual(self.sam.post(f"{self.base}/members", json={"display_name": "X"}).status_code, 403)
        renamed = self.alex.patch(f"{self.base}/members/{person['user_id']}", json={"display_name": "Oma"})
        self.assertIn("Oma", [m["display_name"] for m in renamed.json()["members"]])
        response = self.alex.patch(f"{self.base}/members/{self.sam_id}", json={"display_name": "Samantha"})
        self.assertEqual(code(response, 409), "member_has_account")
        self.trip(self.alex, 10000, 10100, [(person["user_id"], 1)])
        self.fuel(self.alex, 1000, self.alex_id)
        balance = by_name(self.alex.get(f"{self.base}/balance").json()["members"])
        self.assertEqual(balance["Oma"], -1000)

    def test_counts_against_the_member_limit(self):
        with mock.patch.dict("os.environ", {"MAX_MEMBERS_PER_GROUP": "2"}):
            response = self.alex.post(f"{self.base}/members", json={"display_name": "Grandma"})
            self.assertEqual(code(response, 409), "limit_reached")

    def test_placeholder_admin_does_not_count(self):
        person = self.add()
        self.alex.patch(f"{self.base}/members/{person['user_id']}", json={"role": "admin"})
        response = self.alex.patch(f"{self.base}/members/{self.alex_id}", json={"role": "member"})
        self.assertEqual(code(response, 409), "last_admin")

    def test_group_with_only_placeholders_goes_with_the_last_account(self):
        self.add()
        self.alex.patch(f"{self.base}/members/{self.sam_id}", json={"active": False})
        preview = self.alex.get("/v1/account/deletion-preview").json()
        self.assertEqual([g["id"] for g in preview["groups_deleted"]], [self.gid])


class ExportFlagsTests(GroupSetupMixin, unittest.TestCase):
    def test_export_marks_placeholders(self):
        self.alex.post(f"{self.base}/members", json={"display_name": "Grandma"})
        members = self.alex.get(f"{self.base}/export.json").json()["members"]
        self.assertEqual(sorted(m["placeholder"] for m in members), [False, False, True])


if __name__ == "__main__":
    unittest.main()

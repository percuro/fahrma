import unittest
from datetime import date

from app import __version__
from tests.support import PASSWORD, TEST_ORIGIN, ApiTestEnvironment


class GroupSetupMixin:
    """Group with alex (admin) and sam (joined by invitation), one car from km 10,000."""

    def setUp(self):
        self.env = ApiTestEnvironment()
        self.env.create_user("alex", display_name="Alex")
        self.alex = self.env.client("alex")
        group = self.alex.post("/v1/groups", json={"name": "Test group"}).json()
        self.gid = group["id"]
        self.alex_id = group["members"][0]["user_id"]
        invite = self.alex.post(f"/v1/groups/{self.gid}/invites").json()
        self.sam = self.env.client(None)
        response = self.sam.post(
            "/v1/auth/register",
            json={"token": invite["token"], "username": "sam", "display_name": "Sam", "password": PASSWORD},
        )
        assert response.status_code == 201, response.text
        self.sam_id = response.json()["id"]
        car = self.alex.post(
            f"/v1/groups/{self.gid}/cars", json={"name": "Test car", "plate": "TEST-1", "start_odometer_km": 10000}
        )
        assert car.status_code == 201, car.text
        self.car_id = car.json()["id"]
        self.base = f"/v1/groups/{self.gid}"

    def tearDown(self):
        self.env.close()

    def trip(self, client, start, end, shares, day="2026-11-10", external=(), expect=201):
        response = client.post(
            f"{self.base}/trips",
            json={
                "car_id": self.car_id,
                "date": day,
                "start_km": start,
                "end_km": end,
                "shares": [{"user_id": uid, "weight": w} for uid, w in shares],
                "external": list(external),
            },
        )
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def fuel(self, client, cents, payer, day="2026-11-12"):
        response = client.post(
            f"{self.base}/fuel",
            json={
                "car_id": self.car_id,
                "date": day,
                "amount_cents": cents,
                "paid_by_user_id": payer,
                "quantity_milli": 40000,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()


class AuthAndGroupTests(GroupSetupMixin, unittest.TestCase):
    def test_me_lists_groups(self):
        me = self.sam.get("/v1/auth/me").json()
        self.assertEqual(me["display_name"], "Sam")
        self.assertEqual(me["groups"], [{"id": self.gid, "name": "Test group", "role": "member"}])

    def test_invite_is_single_use(self):
        invite = self.alex.post(f"{self.base}/invites").json()
        self.assertTrue(self.env.client(None).get(f"/v1/invites/{invite['token']}").json()["valid"])
        first = self.env.client(None).post(
            "/v1/auth/register",
            json={"token": invite["token"], "username": "kim", "display_name": "Kim", "password": PASSWORD},
        )
        self.assertEqual(first.status_code, 201)
        second = self.env.client(None).post(
            "/v1/auth/register",
            json={"token": invite["token"], "username": "eve", "display_name": "Eve", "password": PASSWORD},
        )
        self.assertEqual(second.status_code, 410)

    def test_members_cannot_invite_or_add_cars(self):
        self.assertEqual(self.sam.post(f"{self.base}/invites").status_code, 403)
        response = self.sam.post(f"{self.base}/cars", json={"name": "X", "start_odometer_km": 0})
        self.assertEqual(response.status_code, 403)

    def test_foreign_group_is_invisible(self):
        self.env.create_user("eve")
        eve = self.env.client("eve")
        self.assertEqual(eve.get(self.base).status_code, 404)
        self.assertEqual(eve.get(f"{self.base}/trips").status_code, 404)

    def test_last_admin_cannot_be_demoted(self):
        response = self.alex.patch(f"{self.base}/members/{self.alex_id}", json={"role": "member"})
        self.assertEqual(response.status_code, 409)

    def test_csrf_header_required(self):
        from fastapi.testclient import TestClient

        from app.main import app

        bare = TestClient(app, headers={"Origin": TEST_ORIGIN})
        bare.cookies = self.alex.cookies
        self.assertEqual(bare.post(f"{self.base}/invites").status_code, 403)


class TripTests(GroupSetupMixin, unittest.TestCase):
    def test_overlap_rejected_and_adjacent_allowed(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        self.trip(self.sam, 10050, 10150, [(self.sam_id, 1)], expect=409)
        self.trip(self.sam, 10100, 10150, [(self.sam_id, 1)])
        self.trip(self.sam, 9000, 9100, [(self.sam_id, 1)], expect=422)

    def test_open_trip_blocks_later_trips_until_finished(self):
        open_trip = self.trip(self.alex, 10000, None, [(self.alex_id, 1)])
        self.assertEqual(self.alex.get(f"{self.base}/cars").json()[0]["open_trip_id"], open_trip["id"])
        self.trip(self.sam, 10200, 10300, [(self.sam_id, 1)], expect=409)
        finished = self.alex.post(f"{self.base}/trips/{open_trip['id']}/finish", json={"end_km": 10120})
        self.assertEqual(finished.json()["km"], 120)
        self.trip(self.sam, 10120, 10300, [(self.sam_id, 1)])
        self.assertEqual(self.alex.get(f"{self.base}/cars").json()[0]["last_km"], 10300)

    def test_update_trip_keeps_shares_consistent(self):
        trip = self.trip(self.alex, 10000, 10100, [(self.alex_id, 1), (self.sam_id, 1)])
        response = self.alex.put(
            f"{self.base}/trips/{trip['id']}",
            json={
                "car_id": self.car_id,
                "date": "2026-11-10",
                "start_km": 10000,
                "end_km": 10110,
                "shares": [{"user_id": self.sam_id, "weight": 2}, {"user_id": self.alex_id, "weight": 1}],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            sorted((s["user_id"], s["weight"]) for s in response.json()["shares"]),
            sorted([(self.sam_id, 2), (self.alex_id, 1)]),
        )

    def test_share_with_non_member_rejected(self):
        self.trip(self.alex, 10000, 10100, [(9999, 1)], expect=422)


class SettlementFlowTests(GroupSetupMixin, unittest.TestCase):
    def test_full_cycle(self):
        # alex 300 km alone, sam 100 km + 100 km together, sam takes a hitchhiker along (10 €)
        self.trip(self.alex, 10000, 10300, [(self.alex_id, 1)])
        self.trip(
            self.sam,
            10300,
            10400,
            [(self.sam_id, 1)],
            external=[{"payer_name": "Anhalter", "amount_cents": 1000, "received_by_user_id": self.sam_id}],
        )
        self.trip(self.alex, 10400, 10500, [(self.alex_id, 1), (self.sam_id, 1)])
        self.fuel(self.alex, 10000, self.alex_id)  # 100 € over 500 km -> 20 ct/km
        expense = self.sam.post(
            f"{self.base}/expenses",
            json={
                "date": "2026-11-01",
                "category": "insurance",
                "amount_cents": 6000,
                "paid_by_user_id": self.sam_id,
                "allocation": "equal",
            },
        )
        self.assertEqual(expense.status_code, 201, expense.text)

        balance = self.alex.get(f"{self.base}/balance").json()
        self.assertEqual(balance["cars"][0]["rate_cents_per_km"], 20.0)
        members = {m["user_id"]: m for m in balance["members"]}
        # alex: trips 60 + 10 = 70 €, insurance 30 € -> owes 100, paid 100 -> 0
        # sam: trips 20 + 10 - 10 credit + 10 held = 30, insurance 30 -> 60, paid 60 -> 0
        self.assertEqual(members[self.alex_id]["balance_cents"], 0)
        self.assertEqual(members[self.sam_id]["balance_cents"], 0)
        self.assertEqual(balance["transfers"], [])
        self.assertEqual(balance["total_cost_cents"], 16000)

        # A second fuel entry by sam makes alex the debtor
        self.fuel(self.sam, 5000, self.sam_id)
        balance = self.alex.get(f"{self.base}/balance").json()
        self.assertEqual(balance["cars"][0]["rate_cents_per_km"], 30.0)
        self.assertEqual(
            balance["transfers"],
            [
                {
                    "id": None,
                    "from_user_id": self.alex_id,
                    "to_user_id": self.sam_id,
                    "amount_cents": 3500,
                    "paid_at": None,
                    "settlement_id": None,
                }
            ],
        )

        created = self.sam.post(f"{self.base}/settlements", json={"period_end": "2026-11-24"})
        self.assertEqual(created.status_code, 201, created.text)
        settlement = created.json()
        self.assertTrue(settlement["is_latest"])
        self.assertEqual(settlement["period_start"], "2026-11-01")
        transfer = settlement["transfers"][0]
        self.assertEqual(transfer["amount_cents"], 3500)

        trips = self.alex.get(f"{self.base}/trips").json()
        self.assertTrue(all(t["settlement_id"] == settlement["id"] and not t["cost_is_estimate"] for t in trips))
        self.assertEqual(sorted(t["cost_cents"] for t in trips), [3000, 3000, 9000])

        # Settled entries are read-only
        self.assertEqual(self.alex.delete(f"{self.base}/trips/{trips[0]['id']}").status_code, 409)
        # The new preview is empty but shows the car's last rate
        after = self.alex.get(f"{self.base}/balance").json()
        self.assertEqual(after["trip_count"], 0)
        self.assertEqual(after["cars"][0]["km"], 0)
        self.assertEqual(after["cars"][0]["last_rate_cents_per_km"], 30.0)

        # Mark the transfer as paid
        self.assertEqual(len(self.alex.get(f"{self.base}/transfers/open").json()), 1)
        paid = self.alex.post(f"{self.base}/transfers/{transfer['id']}/paid")
        self.assertIsNotNone(paid.json()["paid_at"])
        self.assertEqual(self.alex.get(f"{self.base}/transfers/open").json(), [])

        # Only admins may undo; afterwards everything is open again
        self.assertEqual(self.sam.delete(f"{self.base}/settlements/{settlement['id']}").status_code, 403)
        self.assertEqual(self.alex.delete(f"{self.base}/settlements/{settlement['id']}").status_code, 204)
        self.assertEqual(self.alex.get(f"{self.base}/balance").json()["trip_count"], 3)

        audit = self.alex.get(f"{self.base}/audit").json()
        self.assertEqual(audit[0]["entity"], "settlement")
        self.assertEqual(audit[0]["action"], "delete")

    def test_open_trip_blocks_settlement(self):
        self.trip(self.alex, 10000, None, [(self.alex_id, 1)])
        self.fuel(self.alex, 1000, self.alex_id)
        response = self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-24"})
        self.assertEqual(response.status_code, 409)

    def test_gap_needs_confirmation(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        self.trip(self.sam, 10150, 10200, [(self.sam_id, 1)])
        self.fuel(self.alex, 1500, self.alex_id)
        warnings = self.alex.get(f"{self.base}/balance").json()["warnings"]
        self.assertEqual([(w["code"], w["from_km"], w["to_km"]) for w in warnings], [("km_gap", 10100, 10150)])
        self.assertEqual(self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-24"}).status_code, 409)
        response = self.alex.post(
            f"{self.base}/settlements", json={"period_end": "2026-11-24", "accept_warnings": True}
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_fuel_without_km_is_carried_into_next_settlement(self):
        self.fuel(self.alex, 4000, self.alex_id, day="2026-11-05")
        self.trip(self.sam, 10000, 10100, [(self.sam_id, 1)], day="2026-11-02")
        self.env.today = date(2026, 11, 3)
        first = self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-03"})
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["transfers"], [])  # trip without fuel costs in the period
        self.env.today = date(2026, 11, 24)
        self.trip(self.alex, 10100, 10200, [(self.alex_id, 1)], day="2026-11-20")
        balance = self.alex.get(f"{self.base}/balance").json()
        self.assertEqual(balance["fuel_count"], 1)
        self.assertEqual(balance["cars"][0]["rate_cents_per_km"], 40.0)

    def test_future_period_end_rejected(self):
        self.fuel(self.alex, 1000, self.alex_id)
        response = self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-12-01"})
        self.assertEqual(response.status_code, 422)

    def test_trip_expense_follows_trip_shares(self):
        trip = self.trip(self.alex, 10000, 10100, [(self.alex_id, 1), (self.sam_id, 3)])
        response = self.alex.post(
            f"{self.base}/expenses",
            json={
                "date": "2026-11-10",
                "category": "parking",
                "amount_cents": 800,
                "paid_by_user_id": self.alex_id,
                "allocation": "trip",
                "trip_id": trip["id"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        members = {m["user_id"]: m for m in self.alex.get(f"{self.base}/balance").json()["members"]}
        self.assertEqual(members[self.sam_id]["balance_cents"], -600)
        self.assertEqual(self.alex.delete(f"{self.base}/trips/{trip['id']}").status_code, 409)

    def test_csv_export(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        self.fuel(self.alex, 1234, self.alex_id)
        response = self.alex.get(f"{self.base}/export.csv")
        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8-sig")
        self.assertIn("Tanken/Laden;2026-11-12;Test car", text)
        self.assertIn("12,34", text)
        english = self.alex.get(f"{self.base}/export.csv?lang=en").content.decode("utf-8-sig")
        self.assertTrue(english.startswith("Type,Date,Car"))
        self.assertIn("Amount EUR", english)
        self.assertIn("Fuel/charging,2026-11-12,Test car", english)
        self.assertIn(",40.00,l,", english)
        self.assertIn("12.34", english)
        self.assertEqual(self.alex.get(f"{self.base}/export.csv?lang=xx").status_code, 422)


class ErrorCodeTests(GroupSetupMixin, unittest.TestCase):
    """Errors carry a stable code and parameters that the interface translates."""

    def detail(self, response, status_code):
        self.assertEqual(response.status_code, status_code, response.text)
        return response.json()["detail"]

    def test_overlap_and_running_trip(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        response = self.alex.post(
            f"{self.base}/trips",
            json={"car_id": self.car_id, "date": "2026-11-11", "start_km": 10050, "end_km": 10200,
                  "shares": [{"user_id": self.alex_id, "weight": 1}]},
        )  # fmt: skip
        detail = self.detail(response, 409)
        self.assertEqual(detail["code"], "trip_overlap")
        self.assertEqual(detail["params"], {"start_km": 10000, "end_km": 10100, "date": "2026-11-10"})
        self.assertIn("Overlaps", detail["message"])
        self.trip(self.alex, 10100, None, [(self.alex_id, 1)])
        response = self.alex.post(
            f"{self.base}/trips",
            json={"car_id": self.car_id, "date": "2026-11-11", "start_km": 10200, "end_km": 10300,
                  "shares": [{"user_id": self.alex_id, "weight": 1}]},
        )  # fmt: skip
        self.assertEqual(self.detail(response, 409)["code"], "trip_running")

    def test_permission_and_login_errors(self):
        self.assertEqual(self.detail(self.sam.post(f"{self.base}/invites"), 403)["code"], "admin_only")
        self.assertEqual(self.detail(self.sam.get("/v1/groups/999"), 404)["code"], "group_not_found")
        anonymous = self.env.client(None)
        self.assertEqual(self.detail(anonymous.get("/v1/auth/me"), 401)["code"], "not_authenticated")
        response = anonymous.post("/v1/auth/login", json={"username": "alex", "password": "wrong-password"})
        self.assertEqual(self.detail(response, 401)["code"], "invalid_credentials")

    def test_register_password_too_short(self):
        invite = self.alex.post(f"{self.base}/invites").json()
        self.assertTrue(invite["url"].endswith(f"/invite/{invite['token']}"))
        response = self.env.client(None).post(
            "/v1/auth/register",
            json={"token": invite["token"], "username": "kim", "display_name": "Kim", "password": "short"},
        )
        detail = self.detail(response, 422)
        self.assertEqual(detail["code"], "password_too_short")
        self.assertEqual(detail["params"], {"min_length": 12})

    def test_warnings_have_params(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        self.trip(self.alex, 10150, 10200, [(self.alex_id, 1)])
        warnings = self.alex.get(f"{self.base}/balance").json()["warnings"]
        gap = next(w for w in warnings if w["code"] == "km_gap")
        self.assertEqual(gap["params"], {"car": "Test car", "from_km": 10100, "to_km": 10150})


class HealthTests(unittest.TestCase):
    def test_health(self):
        env = ApiTestEnvironment()
        try:
            self.assertEqual(env.client(None).get("/health").json(), {"status": "ok", "version": __version__})
        finally:
            env.close()

    def test_api_docs_hidden_by_default(self):
        env = ApiTestEnvironment()
        try:
            client = env.client(None)
            self.assertEqual(client.get("/docs").status_code, 404)
            self.assertEqual(client.get("/openapi.json").status_code, 404)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()

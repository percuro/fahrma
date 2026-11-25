"""No account can read or change another group's data.

Every API route with an ID in its path must appear in ROUTES below. The test reads the
routes from the app's OpenAPI schema and fails when one is missing, so a new route cannot
slip through untested. Foreign IDs give 404 (not 403), so IDs cannot be probed.
"""

import unittest

from app.main import app
from tests.support import PASSWORD, ApiTestEnvironment, accept

TRIP = {"date": "2026-11-10", "start_km": 0, "end_km": 10, "shares": [{"user_id": 1, "weight": 1}], "external": []}
FUEL = {"date": "2026-11-10", "amount_cents": 100, "paid_by_user_id": 1, "quantity_milli": 1000}
EXPENSE = {"date": "2026-11-10", "category": "other", "amount_cents": 100, "paid_by_user_id": 1, "allocation": "equal"}

# (method, path) -> (expected status for an outsider, request body)
ROUTES = {
    ("GET", "/v1/groups/{group_id}"): (404, None),
    ("PATCH", "/v1/groups/{group_id}"): (404, {"name": "taken over"}),
    ("DELETE", "/v1/groups/{group_id}"): (404, {"name": "Bert's group"}),
    ("PATCH", "/v1/groups/{group_id}/members/{user_id}"): (404, {"role": "admin"}),
    ("POST", "/v1/groups/{group_id}/members"): (404, {"display_name": "Mallory"}),
    ("POST", "/v1/groups/{group_id}/members/{user_id}/invite"): (404, None),
    ("GET", "/v1/groups/{group_id}/export.json"): (404, None),
    ("GET", "/v1/groups/{group_id}/export.csv"): (404, None),
    ("POST", "/v1/groups/{group_id}/invites"): (404, None),
    ("GET", "/v1/groups/{group_id}/audit"): (404, None),
    ("GET", "/v1/groups/{group_id}/cars"): (404, None),
    ("POST", "/v1/groups/{group_id}/cars"): (404, {"name": "Mine", "start_odometer_km": 0}),
    ("PUT", "/v1/groups/{group_id}/cars/{car_id}"): (404, {"name": "Mine", "start_odometer_km": 0}),
    ("GET", "/v1/groups/{group_id}/cars/{car_id}/stats"): (404, None),
    ("GET", "/v1/groups/{group_id}/trips"): (404, None),
    ("POST", "/v1/groups/{group_id}/trips"): (404, {**TRIP, "car_id": 1}),
    ("GET", "/v1/groups/{group_id}/trips/{trip_id}"): (404, None),
    ("PUT", "/v1/groups/{group_id}/trips/{trip_id}"): (404, {**TRIP, "car_id": 1}),
    ("DELETE", "/v1/groups/{group_id}/trips/{trip_id}"): (404, None),
    ("POST", "/v1/groups/{group_id}/trips/{trip_id}/finish"): (404, {"end_km": 99999}),
    ("GET", "/v1/groups/{group_id}/fuel"): (404, None),
    ("POST", "/v1/groups/{group_id}/fuel"): (404, {**FUEL, "car_id": 1}),
    ("GET", "/v1/groups/{group_id}/fuel/{fuel_id}"): (404, None),
    ("PUT", "/v1/groups/{group_id}/fuel/{fuel_id}"): (404, {**FUEL, "car_id": 1}),
    ("DELETE", "/v1/groups/{group_id}/fuel/{fuel_id}"): (404, None),
    ("GET", "/v1/groups/{group_id}/expenses"): (404, None),
    ("POST", "/v1/groups/{group_id}/expenses"): (404, EXPENSE),
    ("GET", "/v1/groups/{group_id}/expenses/{expense_id}"): (404, None),
    ("PUT", "/v1/groups/{group_id}/expenses/{expense_id}"): (404, EXPENSE),
    ("DELETE", "/v1/groups/{group_id}/expenses/{expense_id}"): (404, None),
    ("GET", "/v1/groups/{group_id}/balance"): (404, None),
    ("GET", "/v1/groups/{group_id}/transfers/open"): (404, None),
    ("POST", "/v1/groups/{group_id}/transfers/{transfer_id}/paid"): (404, None),
    ("DELETE", "/v1/groups/{group_id}/transfers/{transfer_id}/paid"): (404, None),
    ("GET", "/v1/groups/{group_id}/settlements"): (404, None),
    ("POST", "/v1/groups/{group_id}/settlements"): (404, {"period_end": "2026-11-20", "accept_warnings": True}),
    ("GET", "/v1/groups/{group_id}/settlements/{settlement_id}"): (404, None),
    ("DELETE", "/v1/groups/{group_id}/settlements/{settlement_id}"): (404, None),
    ("DELETE", "/v1/account/sessions/{session_id}"): (404, None),
    # Admin routes act on other accounts by design: a normal account gets 403
    ("PATCH", "/v1/admin/users/{user_id}"): (403, {"is_active": False}),
    ("DELETE", "/v1/admin/users/{user_id}"): (403, None),
    ("POST", "/v1/admin/users/{user_id}/password-reset"): (403, None),
    ("DELETE", "/v1/admin/invitations/{invitation_id}"): (403, None),
}

# Routes inside a group that take the ID of an object of that group
OBJECT_ROUTES = {
    ("PUT", "/v1/groups/{group_id}/cars/{car_id}"),
    ("GET", "/v1/groups/{group_id}/cars/{car_id}/stats"),
    ("GET", "/v1/groups/{group_id}/trips/{trip_id}"),
    ("PUT", "/v1/groups/{group_id}/trips/{trip_id}"),
    ("DELETE", "/v1/groups/{group_id}/trips/{trip_id}"),
    ("POST", "/v1/groups/{group_id}/trips/{trip_id}/finish"),
    ("GET", "/v1/groups/{group_id}/fuel/{fuel_id}"),
    ("PUT", "/v1/groups/{group_id}/fuel/{fuel_id}"),
    ("DELETE", "/v1/groups/{group_id}/fuel/{fuel_id}"),
    ("GET", "/v1/groups/{group_id}/expenses/{expense_id}"),
    ("PUT", "/v1/groups/{group_id}/expenses/{expense_id}"),
    ("DELETE", "/v1/groups/{group_id}/expenses/{expense_id}"),
    ("POST", "/v1/groups/{group_id}/transfers/{transfer_id}/paid"),
    ("DELETE", "/v1/groups/{group_id}/transfers/{transfer_id}/paid"),
    ("GET", "/v1/groups/{group_id}/settlements/{settlement_id}"),
    ("DELETE", "/v1/groups/{group_id}/settlements/{settlement_id}"),
    ("PATCH", "/v1/groups/{group_id}/members/{user_id}"),
    ("POST", "/v1/groups/{group_id}/members/{user_id}/invite"),
}


def routes_with_ids() -> set[tuple[str, str]]:
    # The OpenAPI schema lists every API route with its full path, however routers are nested
    paths = app.openapi()["paths"]
    return {(method.upper(), path) for path, operations in paths.items() if "{" in path for method in operations}


class IsolationTest(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()
        self.env.create_user("anna", role="admin")
        self.env.create_user("bert")
        self.anna = self.env.client("anna")
        self.bert = self.env.client("bert")
        # Bert's group with a member, a car and one of everything
        group = self.bert.post("/v1/groups", json={"name": "Bert's group"}).json()
        gid, bert_id = group["id"], group["members"][0]["user_id"]
        base = f"/v1/groups/{gid}"
        invite = self.bert.post(f"{base}/invites").json()
        accept(self.env.client(None), invite["url"], username="carl", password=PASSWORD)
        car = self.bert.post(f"{base}/cars", json={"name": "Bert's car", "start_odometer_km": 0}).json()
        shares = [{"user_id": bert_id, "weight": 1}]
        trip = self.bert.post(
            f"{base}/trips", json={**TRIP, "car_id": car["id"], "start_km": 0, "end_km": 100, "shares": shares}
        ).json()
        fuel = self.bert.post(f"{base}/fuel", json={**FUEL, "car_id": car["id"], "paid_by_user_id": bert_id}).json()
        expense = self.bert.post(f"{base}/expenses", json={**EXPENSE, "paid_by_user_id": bert_id}).json()
        carl_id = next(m["user_id"] for m in self.bert.get(base).json()["members"] if m["user_id"] != bert_id)
        self.bert.post(
            f"{base}/trips",
            json={**TRIP, "car_id": car["id"], "start_km": 100, "end_km": 200,
                  "shares": [{"user_id": carl_id, "weight": 1}]},
        )  # fmt: skip
        settlement = self.bert.post(f"{base}/settlements", json={"period_end": "2026-11-20"}).json()
        self.bert_ids = {
            "group_id": gid,
            "user_id": carl_id,
            "car_id": car["id"],
            "trip_id": trip["id"],
            "fuel_id": fuel["id"],
            "expense_id": expense["id"],
            "transfer_id": settlement["transfers"][0]["id"],
            "settlement_id": settlement["id"],
            "session_id": self.bert.get("/v1/account/sessions").json()[0]["id"],
            "invitation_id": self.anna.post("/v1/admin/invitations", json={}).json()["id"],
        }
        self.before = self.bert.get(f"{base}/export.json").json()
        # Anna's own group, to try Bert's object IDs inside a group she belongs to
        self.anna_gid = self.anna.post("/v1/groups", json={"name": "Anna's group"}).json()["id"]

    def tearDown(self):
        self.env.close()

    def test_every_route_with_an_id_is_covered(self):
        self.assertEqual(routes_with_ids() - set(ROUTES), set(), "add the new route to ROUTES")
        self.assertEqual(set(OBJECT_ROUTES) - set(ROUTES), set())

    def test_outsider_gets_404_for_a_foreign_group(self):
        self.env.create_user("dora")
        outsider = self.env.client("dora")
        for (method, path), (expected, body) in ROUTES.items():
            with self.subTest(method=method, path=path):
                url = path.format(**self.bert_ids)
                response = outsider.request(method, url, json=body)
                self.assertEqual(response.status_code, expected, response.text)

    def test_foreign_object_ids_inside_own_group_give_404(self):
        for method, path in sorted(OBJECT_ROUTES):
            _status, body = ROUTES[(method, path)]
            with self.subTest(method=method, path=path):
                url = path.format(**{**self.bert_ids, "group_id": self.anna_gid})
                response = self.anna.request(method, url, json=body)
                self.assertEqual(response.status_code, 404, response.text)

    def test_nothing_changed(self):
        self.env.create_user("dora")
        outsider = self.env.client("dora")
        for (method, path), (_expected, body) in ROUTES.items():
            if not path.startswith("/v1/admin"):
                outsider.request(method, path.format(**self.bert_ids), json=body)
        after = self.bert.get(f"/v1/groups/{self.bert_ids['group_id']}/export.json").json()
        for key in ("group", "members", "cars", "trips", "fuel", "expenses", "settlements", "settlement_transfers"):
            self.assertEqual(after[key], self.before[key], key)


if __name__ == "__main__":
    unittest.main()

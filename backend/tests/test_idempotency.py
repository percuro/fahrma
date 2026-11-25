"""Offline drafts are sent with an Idempotency-Key: sending one twice saves it once."""

import unittest

from tests.test_api import GroupSetupMixin

KEY = "draft-0001-abcdef"


class IdempotencyTest(GroupSetupMixin, unittest.TestCase):
    def trip_body(self, start=10000, end=10050):
        return {
            "car_id": self.car_id,
            "date": "2026-11-10",
            "start_km": start,
            "end_km": end,
            "shares": [{"user_id": self.alex_id, "weight": 1}],
        }

    def post(self, path, body, key=KEY, client=None):
        return (client or self.alex).post(f"{self.base}{path}", json=body, headers={"Idempotency-Key": key})

    def test_trip_sent_twice_is_saved_once(self):
        first = self.post("/trips", self.trip_body())
        self.assertEqual(first.status_code, 201, first.text)
        # The answer got lost; the draft is sent again (even unchanged it would overlap the first trip)
        again = self.post("/trips", self.trip_body())
        self.assertEqual(again.status_code, 201, again.text)
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual(len(self.alex.get(f"{self.base}/trips").json()), 1)
        # Without the key the same trip is a real overlap
        self.assertEqual(self.alex.post(f"{self.base}/trips", json=self.trip_body()).status_code, 409)

    def test_fuel_and_expense_sent_twice(self):
        fuel = {"car_id": self.car_id, "date": "2026-11-12", "amount_cents": 6000, "paid_by_user_id": self.alex_id}
        expense = {
            "date": "2026-11-12",
            "category": "parking",
            "amount_cents": 500,
            "paid_by_user_id": self.alex_id,
            "allocation": "equal",
        }
        for path, body, key in (("/fuel", fuel, "fuel-key-1"), ("/expenses", expense, "expense-key-1")):
            first = self.post(path, body, key)
            again = self.post(path, body, key)
            self.assertEqual((first.status_code, again.status_code), (201, 201), again.text)
            self.assertEqual(first.json()["id"], again.json()["id"])
            self.assertEqual(len(self.alex.get(f"{self.base}{path}").json()), 1)

    def test_finish_sent_twice(self):
        trip = self.trip(self.alex, 10000, None, [(self.alex_id, 1)])
        path = f"/trips/{trip['id']}/finish"
        first = self.post(path, {"end_km": 10080}, "finish-key-1")
        again = self.post(path, {"end_km": 10080}, "finish-key-1")
        self.assertEqual((first.status_code, again.status_code), (200, 200), again.text)
        self.assertEqual(again.json()["end_km"], 10080)
        # A new key for an already finished trip is a real conflict
        self.assertEqual(self.post(path, {"end_km": 10090}, "finish-key-2").status_code, 409)

    def test_deleted_since_is_not_created_again(self):
        first = self.post("/trips", self.trip_body()).json()
        self.assertEqual(self.alex.delete(f"{self.base}/trips/{first['id']}").status_code, 204)
        again = self.post("/trips", self.trip_body())
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"]["code"], "already_sent")
        self.assertEqual(self.alex.get(f"{self.base}/trips").json(), [])

    def test_key_is_per_person_and_kind(self):
        self.assertEqual(self.post("/trips", self.trip_body()).status_code, 201)
        # Another person may (by chance) use the same key: it is a separate entry
        other = self.post("/trips", self.trip_body(10050, 10100), client=self.sam)
        self.assertEqual(other.status_code, 201, other.text)
        self.assertEqual(len(self.alex.get(f"{self.base}/trips").json()), 2)
        # The same key for something else is rejected
        fuel = {"car_id": self.car_id, "date": "2026-11-12", "amount_cents": 6000, "paid_by_user_id": self.alex_id}
        reused = self.post("/fuel", fuel)
        self.assertEqual(reused.status_code, 422)
        self.assertEqual(reused.json()["detail"]["code"], "idempotency_key_reused")

    def test_invalid_key(self):
        for key in ("short", "x" * 65, "with space 123", "semi;colon-123"):
            response = self.post("/trips", self.trip_body(), key)
            self.assertEqual(response.status_code, 422, key)
            self.assertEqual(response.json()["detail"]["code"], "invalid_idempotency_key")

    def test_keys_go_with_the_group(self):
        self.assertEqual(self.post("/trips", self.trip_body()).status_code, 201)
        group = self.alex.get(self.base).json()
        response = self.alex.request("DELETE", self.base, json={"name": group["name"]})
        self.assertEqual(response.status_code, 204, response.text)


if __name__ == "__main__":
    unittest.main()

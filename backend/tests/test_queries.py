"""Lists must not run one query per row: the number of queries stays the same for more rows."""

import unittest
from contextlib import contextmanager

from sqlalchemy import event

from tests.support import PASSWORD, ApiTestEnvironment, accept


class QueryCountTest(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()
        self.env.create_user("alex", role="admin")
        self.alex = self.env.client("alex")
        self.gid = self.alex.post("/v1/groups", json={"name": "Family"}).json()["id"]
        url = self.alex.post(f"/v1/groups/{self.gid}/invites").json()["url"]
        accept(self.env.client(username=None), url, username="sam", password=PASSWORD)
        self.ids = [m["user_id"] for m in self.alex.get(f"/v1/groups/{self.gid}").json()["members"]]
        car = self.alex.post(f"/v1/groups/{self.gid}/cars", json={"name": "Car", "start_odometer_km": 0})
        self.car = car.json()["id"]
        self.km = 0

    def tearDown(self):
        self.env.close()

    @contextmanager
    def counting(self):
        counter = {"queries": 0}

        def count(*_args, **_kwargs):
            counter["queries"] += 1

        event.listen(self.env.engine, "before_cursor_execute", count)
        try:
            yield counter
        finally:
            event.remove(self.env.engine, "before_cursor_execute", count)

    def queries(self, path: str) -> int:
        with self.counting() as counter:
            self.assertEqual(self.alex.get(path).status_code, 200)
        return counter["queries"]

    def add_entries(self, count: int) -> None:
        group = f"/v1/groups/{self.gid}"
        shares = [{"user_id": user_id, "weight": 1} for user_id in self.ids]
        for _ in range(count):
            trip = {
                "car_id": self.car,
                "date": "2026-11-01",
                "start_km": self.km,
                "end_km": self.km + 10,
                "shares": shares,
            }
            self.alex.post(f"{group}/trips", json=trip)
            fuel = {"car_id": self.car, "date": "2026-11-01", "amount_cents": 500, "paid_by_user_id": self.ids[1]}
            self.alex.post(f"{group}/fuel", json=fuel)
            expense = {"date": "2026-11-01", "category": "wash", "amount_cents": 500, "paid_by_user_id": self.ids[0]}
            self.alex.post(f"{group}/expenses", json={**expense, "car_id": self.car, "allocation": "equal"})
            self.km += 10

    def test_group_lists_and_exports(self):
        paths = [
            f"/v1/groups/{self.gid}/trips",
            f"/v1/groups/{self.gid}/fuel",
            f"/v1/groups/{self.gid}/expenses",
            f"/v1/groups/{self.gid}/balance",
            f"/v1/groups/{self.gid}/export.json",
            "/v1/account/export.json",
        ]
        self.add_entries(2)
        few = {path: self.queries(path) for path in paths}
        self.add_entries(6)
        many = {path: self.queries(path) for path in paths}
        self.assertEqual(few, many)

    def test_groups_of_the_instance(self):
        few = self.queries("/v1/admin/groups")
        for number in range(5):
            gid = self.alex.post("/v1/groups", json={"name": f"Group {number}"}).json()["id"]
            self.alex.post(f"/v1/groups/{gid}/cars", json={"name": "Car", "start_odometer_km": 0})
        self.assertEqual(self.queries("/v1/admin/groups"), few)
        self.assertEqual(len(self.alex.get("/v1/admin/groups").json()), 6)

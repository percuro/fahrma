"""Reservations: overlap, local times across daylight saving time, rights and life cycle.

The test clock stands at 2026-11-24 12:00 UTC. Leaving a group and deleting an account use
the real clock, so those tests use one reservation that is over already by any clock
(2026-11-24 13:00) and one far ahead (2030).
"""

import json
import unittest
from datetime import date

from tests.support import PASSWORD, accept
from tests.test_accounts import code
from tests.test_api import GroupSetupMixin


class ReservationMixin(GroupSetupMixin):
    def reserve(self, client, start, end, user_id=None, car_id=None, expect=201, note=None):
        response = client.post(
            f"{self.base}/reservations",
            json={
                "car_id": car_id or self.car_id,
                "user_id": user_id or self.alex_id,
                "starts_at": start,
                "ends_at": end,
                "note": note,
            },
        )
        self.assertEqual(response.status_code, expect, response.text)
        return response

    def body(self, start, end, user_id=None):
        return {"car_id": self.car_id, "user_id": user_id or self.alex_id, "starts_at": start, "ends_at": end}

    def listed(self, client=None, **params):
        response = (client or self.alex).get(f"{self.base}/reservations", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def vienna(self):
        response = self.alex.patch(self.base, json={"timezone": "Europe/Vienna"})
        self.assertEqual(response.status_code, 200, response.text)


class ReservationTest(ReservationMixin, unittest.TestCase):
    def test_local_times_in_and_out(self):
        self.vienna()
        created = self.reserve(self.alex, "2026-12-01T08:00", "2026-12-01T10:30:45", note="  IKEA  ").json()
        self.assertEqual(created["starts_at"], "2026-12-01T08:00:00")
        self.assertEqual(created["ends_at"], "2026-12-01T10:30:00")  # to the minute
        self.assertEqual(created["starts_at_utc"], "2026-12-01T07:00:00Z")
        self.assertEqual((created["note"], created["created_by"]), ("IKEA", self.alex_id))
        read = self.alex.get(f"{self.base}/reservations/{created['id']}").json()
        self.assertEqual(read, created)
        # A time with an offset is that moment
        other = self.reserve(self.alex, "2026-12-02T08:00:00Z", "2026-12-02T11:00:00+01:00").json()
        self.assertEqual((other["starts_at"], other["ends_at"]), ("2026-12-02T09:00:00", "2026-12-02T11:00:00"))

    def test_daylight_saving_time(self):
        self.vienna()
        # 2027-03-28 02:00–03:00 does not exist in Vienna
        response = self.reserve(self.alex, "2027-03-28T02:30", "2027-03-28T05:00", expect=422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_local_time")
        self.assertEqual(response.json()["detail"]["params"], {"time": "2027-03-28T02:30"})
        across = self.reserve(self.alex, "2027-03-28T01:00", "2027-03-28T04:00").json()
        self.assertEqual(
            (across["starts_at_utc"], across["ends_at_utc"]), ("2027-03-28T00:00:00Z", "2027-03-28T02:00:00Z")
        )
        # 2027-10-31 02:00–03:00 happens twice; the first one counts (summer time, +02:00)
        twice = self.reserve(self.alex, "2027-10-31T02:30", "2027-10-31T04:00").json()
        self.assertEqual(twice["starts_at_utc"], "2027-10-31T00:30:00Z")
        self.assertEqual(twice["starts_at"], "2027-10-31T02:30:00")

    def test_overlap_is_refused_touching_is_fine(self):
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00")
        response = self.reserve(self.sam, "2026-12-01T11:00", "2026-12-01T13:00", user_id=self.sam_id, expect=409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "reservation_overlap")
        self.assertEqual(
            detail["params"], {"user_id": self.alex_id, "starts_at": "2026-12-01T10:00", "ends_at": "2026-12-01T12:00"}
        )
        self.reserve(self.sam, "2026-12-01T09:00", "2026-12-01T13:00", user_id=self.sam_id, expect=409)
        self.reserve(self.sam, "2026-12-01T12:00", "2026-12-01T14:00", user_id=self.sam_id)
        self.reserve(self.sam, "2026-12-01T08:00", "2026-12-01T10:00", user_id=self.sam_id)
        other_car = self.alex.post(f"{self.base}/cars", json={"name": "Van", "start_odometer_km": 0}).json()
        self.reserve(self.sam, "2026-12-01T11:00", "2026-12-01T13:00", user_id=self.sam_id, car_id=other_car["id"])

    def test_moving_a_reservation_does_not_collide_with_itself(self):
        created = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00").json()
        response = self.alex.put(
            f"{self.base}/reservations/{created['id']}", json=self.body("2026-12-01T11:00", "2026-12-01T13:00")
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["starts_at"], "2026-12-01T11:00:00")

    def test_invalid_periods(self):
        cases = [
            (("2026-12-01T12:00", "2026-12-01T12:00"), "reservation_end_before_start"),
            (("2026-12-01T12:00", "2026-12-01T10:00"), "reservation_end_before_start"),
            (("2026-11-24T08:00", "2026-11-24T12:00"), "reservation_in_past"),  # now is 12:00 UTC
            (("2026-12-01T00:00", "2027-01-01T00:01"), "reservation_too_long"),
        ]
        for (start, end), expected in cases:
            with self.subTest(expected=expected, start=start, end=end):
                self.assertEqual(self.reserve(self.alex, start, end, expect=422).json()["detail"]["code"], expected)
        # Running already but not over: fine, and exactly 31 days too
        self.reserve(self.alex, "2026-11-24T11:00", "2026-11-24T13:00")
        self.reserve(self.alex, "2026-12-01T00:00", "2027-01-01T00:00")

    def test_car_and_person_must_fit(self):
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", user_id=99999, expect=422)
        self.alex.patch(f"{self.base}/members/{self.sam_id}", json={"active": False})
        response = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", user_id=self.sam_id, expect=422)
        self.assertEqual(response.json()["detail"]["code"], "not_a_member")
        self.alex.put(
            f"{self.base}/cars/{self.car_id}",
            json={"name": "Test car", "start_odometer_km": 10000, "archived": True},
        )
        response = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", expect=409)
        self.assertEqual(response.json()["detail"]["code"], "car_archived")
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", car_id=99999, expect=404)

    def test_who_may_change_it(self):
        alex_own = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00").json()
        for_sam = self.reserve(self.alex, "2026-12-02T10:00", "2026-12-02T12:00", user_id=self.sam_id).json()
        sams = self.reserve(self.sam, "2026-12-03T10:00", "2026-12-03T12:00", user_id=self.sam_id).json()
        url = f"{self.base}/reservations"
        # Sam is neither the person nor whoever entered it, and no admin
        self.assertEqual(
            code(self.sam.put(f"{url}/{alex_own['id']}", json=self.body("2026-12-01T10:00", "2026-12-01T13:00")), 403),
            "reservation_not_yours",
        )
        self.assertEqual(code(self.sam.delete(f"{url}/{alex_own['id']}"), 403), "reservation_not_yours")
        # It is for Sam: Sam may move or cancel it
        moved = self.sam.put(
            f"{url}/{for_sam['id']}", json=self.body("2026-12-02T14:00", "2026-12-02T16:00", self.sam_id)
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        # Admins may change anything
        self.assertEqual(self.alex.delete(f"{url}/{sams['id']}").status_code, 204)
        self.assertEqual(code(self.alex.get(f"{url}/{sams['id']}"), 404), "reservation_not_found")
        audit = [(e["entity"], e["action"]) for e in self.alex.get(f"{self.base}/audit").json()]
        self.assertIn(("reservation", "delete"), audit)

    def test_over_is_over(self):
        created = self.reserve(self.alex, "2026-11-24T13:00", "2026-11-24T14:00").json()
        self.env.today = date(2026, 11, 25)
        url = f"{self.base}/reservations/{created['id']}"
        self.assertEqual(code(self.alex.delete(url), 409), "reservation_ended")
        self.assertEqual(code(self.alex.put(url, json=self.body("2026-11-26T13:00", "2026-11-26T14:00")), 409),
                         "reservation_ended")  # fmt: skip

    def test_listing_by_local_days(self):
        self.vienna()
        late = self.reserve(self.alex, "2026-12-01T23:30", "2026-12-02T00:30").json()
        early = self.reserve(self.alex, "2026-12-03T00:00", "2026-12-03T01:00").json()
        later = self.reserve(self.alex, "2026-12-20T10:00", "2026-12-20T11:00").json()
        ids = lambda rows: [r["id"] for r in rows]  # noqa: E731
        self.assertEqual(ids(self.listed(**{"from": "2026-12-02", "to": "2026-12-02"})), [late["id"]])
        self.assertEqual(ids(self.listed(**{"from": "2026-12-03", "to": "2026-12-03"})), [early["id"]])
        # Default: today (2026-11-24) and the next 13 days
        self.assertEqual(ids(self.listed()), [late["id"], early["id"]])
        self.assertEqual(
            ids(self.listed(**{"from": "2026-12-01", "to": "2026-12-31"})), [late["id"], early["id"], later["id"]]
        )
        self.assertEqual(self.listed(car_id=99999), [])
        too_long = self.alex.get(f"{self.base}/reservations", params={"from": "2026-01-01", "to": "2026-12-31"})
        self.assertEqual(code(too_long, 422), "range_too_long")
        backwards = self.alex.get(f"{self.base}/reservations", params={"from": "2026-12-31", "to": "2026-12-01"})
        self.assertEqual(code(backwards, 422), "invalid_range")


class ReservationLifeCycleTest(ReservationMixin, unittest.TestCase):
    def past_and_upcoming(self, user_id):
        past = self.reserve(self.alex, "2026-11-24T13:00", "2026-11-24T14:00", user_id=user_id).json()
        upcoming = self.reserve(self.alex, "2030-01-01T10:00", "2030-01-01T12:00", user_id=user_id).json()
        return past, upcoming

    def remaining(self):
        return [r["id"] for r in self.listed(**{"from": "2026-11-24", "to": "2026-11-24"})] + [
            r["id"] for r in self.listed(**{"from": "2030-01-01", "to": "2030-01-01"})
        ]

    def test_leaving_the_group_cancels_upcoming_reservations(self):
        past, _upcoming = self.past_and_upcoming(self.sam_id)
        response = self.alex.patch(f"{self.base}/members/{self.sam_id}", json={"active": False})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.remaining(), [past["id"]])

    def test_deleting_the_account_cancels_upcoming_reservations(self):
        past, _upcoming = self.past_and_upcoming(self.sam_id)
        self.assertEqual(self.sam.request("DELETE", "/v1/account", json={"password": PASSWORD}).status_code, 204)
        self.assertEqual(self.remaining(), [past["id"]])
        mine = self.alex.get("/v1/account/export.json").json()
        self.assertEqual([r["id"] for r in mine["reservations"]], [past["id"]])  # alex entered it

    def test_existing_account_takes_over_a_placeholders_reservations(self):
        group = self.alex.post(f"{self.base}/members", json={"display_name": "Grandma"}).json()
        grandma = next(m["user_id"] for m in group["members"] if m["display_name"] == "Grandma")
        created = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", user_id=grandma).json()
        link = self.alex.post(f"{self.base}/members/{grandma}/invite").json()
        self.env.create_user("robin")
        robin = self.env.client("robin")
        self.assertEqual(accept(robin, link["url"]).status_code, 200)
        robin_id = robin.get("/v1/auth/me").json()["id"]
        self.assertEqual(robin.get(f"{self.base}/reservations/{created['id']}").json()["user_id"], robin_id)

    def test_export_import_and_group_deletion(self):
        self.vienna()
        created = self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00", user_id=self.sam_id).json()
        export = self.alex.get(f"{self.base}/export.json").json()
        self.assertEqual(len(export["reservations"]), 1)
        response = self.alex.post(
            f"/v1/groups/import?member={self.alex_id}",
            content=json.dumps(export).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        new = response.json()
        [copy] = self.alex.get(
            f"/v1/groups/{new['id']}/reservations", params={"from": "2026-12-01", "to": "2026-12-01"}
        ).json()
        sam_now = next(m["user_id"] for m in new["members"] if m["display_name"] == "Sam")
        self.assertEqual((copy["starts_at"], copy["ends_at"]), (created["starts_at"], created["ends_at"]))
        self.assertEqual(copy["user_id"], sam_now)
        self.assertNotEqual(copy["id"], created["id"])
        self.assertEqual(self.alex.request("DELETE", self.base, json={"name": "Test group"}).status_code, 204)

    def test_import_refuses_broken_reservations(self):
        self.reserve(self.alex, "2026-12-01T10:00", "2026-12-01T12:00")
        export = self.alex.get(f"{self.base}/export.json").json()
        [row] = export["reservations"]
        cases = [
            ({**row, "user_id": 99999}, "reservations[0].user_id"),
            ({**row, "car_id": 99999}, "reservations[0].car_id"),
            ({**row, "ends_at": row["starts_at"]}, "reservations[0].ends_at"),
        ]
        for broken, where in cases:
            with self.subTest(where=where):
                response = self.alex.post(
                    "/v1/groups/import/check", content=json.dumps({**export, "reservations": [broken]})
                )
                self.assertEqual(code(response, 422), "import_invalid")
                self.assertEqual(response.json()["detail"]["params"]["where"], where)
        overlapping = [row, {**row, "id": row["id"] + 1}]
        response = self.alex.post(
            "/v1/groups/import/check", content=json.dumps({**export, "reservations": overlapping})
        )
        self.assertEqual(response.json()["detail"]["params"]["where"], "reservations[1].starts_at")


if __name__ == "__main__":
    unittest.main()

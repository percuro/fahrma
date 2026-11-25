"""Statistics per car: km, consumption full-to-full, costs by month and person."""

import unittest
from datetime import date
from types import SimpleNamespace

from app.services.stats_service import consumption_intervals, split_km
from tests.test_api import GroupSetupMixin


def fuel(id, day, km, milli, cents=5000, full=True):
    return SimpleNamespace(
        id=id, date=date.fromisoformat(day), odometer_km=km, quantity_milli=milli, amount_cents=cents, full_tank=full
    )


class ConsumptionTest(unittest.TestCase):
    def test_full_to_full(self):
        entries = [
            fuel(1, "2026-01-01", 10000, 40000),
            fuel(2, "2026-01-10", 10300, 10000, 1500, full=False),
            fuel(3, "2026-01-20", 10600, 30000, 4500),
        ]
        [interval] = consumption_intervals(entries)
        # The first full tank only marks the start; partial + next full tank count
        self.assertEqual((interval.km, interval.milli, interval.cents), (600, 40000, 6000))
        self.assertEqual(interval.end, date(2026, 1, 20))

    def test_missing_quantity_or_odometer_breaks_the_interval(self):
        no_quantity = [
            fuel(1, "2026-01-01", 10000, 40000),
            fuel(2, "2026-01-10", 10300, None, full=False),
            fuel(3, "2026-01-20", 10600, 30000),
            fuel(4, "2026-02-01", 11000, 25000),
        ]
        self.assertEqual([(i.km, i.milli) for i in consumption_intervals(no_quantity)], [(400, 25000)])
        no_odometer = [
            fuel(1, "2026-01-01", 10000, 40000),
            fuel(2, "2026-01-10", None, 10000, full=False),
            fuel(3, "2026-01-20", 10600, 30000),
        ]
        self.assertEqual(consumption_intervals(no_odometer), [])

    def test_too_little_data(self):
        self.assertEqual(consumption_intervals([fuel(1, "2026-01-01", 10000, 40000)]), [])
        self.assertEqual(
            consumption_intervals([fuel(1, "2026-01-01", None, 40000), fuel(2, "2026-02-01", None, 1)]), []
        )

    def test_split_km_adds_up(self):
        trips = [
            SimpleNamespace(km=100, shares=[SimpleNamespace(user_id=1, weight=1)] * 1),
            SimpleNamespace(km=10, shares=[SimpleNamespace(user_id=i, weight=1) for i in (1, 2, 3)]),
        ]
        km = split_km(trips)
        self.assertEqual(sum(km.values()), 110)
        self.assertEqual(km, {1: 104, 2: 3, 3: 3})


class StatsApiTest(GroupSetupMixin, unittest.TestCase):
    def add_fuel(self, day, km, milli, cents, full=True):
        response = self.alex.post(
            f"{self.base}/fuel",
            json={
                "car_id": self.car_id,
                "date": day,
                "odometer_km": km,
                "quantity_milli": milli,
                "amount_cents": cents,
                "paid_by_user_id": self.alex_id,
                "full_tank": full,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_year_and_all_years(self):
        self.trip(self.alex, 10000, 10300, [(self.alex_id, 1)], day="2025-12-20")
        self.trip(self.alex, 10300, 10500, [(self.alex_id, 1), (self.sam_id, 1)], day="2026-01-05")
        self.trip(self.sam, 10500, 10900, [(self.sam_id, 1)], day="2026-03-02")
        self.trip(self.sam, 10900, None, [(self.sam_id, 1)], day="2026-03-03")  # still running: not counted
        self.add_fuel("2025-12-19", 10000, 45000, 7000)
        self.add_fuel("2026-01-04", 10300, 20000, 3200)
        self.add_fuel("2026-03-02", 10900, 28000, 4400)
        expense = self.alex.post(
            f"{self.base}/expenses",
            json={
                "car_id": self.car_id,
                "date": "2026-02-01",
                "category": "service",
                "amount_cents": 25000,
                "paid_by_user_id": self.alex_id,
                "allocation": "by_km",
            },
        )
        self.assertEqual(expense.status_code, 201, expense.text)

        year = self.sam.get(f"{self.base}/cars/{self.car_id}/stats?year=2026").json()
        self.assertEqual(year["years"], [2025, 2026])
        self.assertEqual((year["km"], year["trips"]), (600, 2))
        self.assertEqual((year["fuel_cents"], year["fuel_entries"]), (7600, 2))
        self.assertEqual((year["priced_milli"], year["priced_cents"]), (48000, 7600))
        # Both intervals end in 2026: 10,000 → 10,300 and 10,300 → 10,900
        self.assertEqual(year["consumption"], {"milli": 48000, "km": 900, "cents": 7600, "intervals": 2})
        self.assertEqual(year["expense_cents"], 25000)
        self.assertEqual(year["categories"], [{"category": "service", "cents": 25000}])
        self.assertEqual(year["members"], [{"user_id": self.sam_id, "km": 500}, {"user_id": self.alex_id, "km": 100}])
        self.assertEqual(len(year["periods"]), 12)
        self.assertEqual(year["periods"][0], {"period": "2026-01", "km": 200, "fuel_cents": 3200, "expense_cents": 0})
        self.assertEqual(year["periods"][1]["expense_cents"], 25000)

        total = self.alex.get(f"{self.base}/cars/{self.car_id}/stats").json()
        self.assertIsNone(total["year"])
        self.assertEqual(total["km"], 900)
        self.assertEqual([p["period"] for p in total["periods"]], ["2025", "2026"])
        self.assertEqual(total["periods"][0]["km"], 300)

    def test_empty_car(self):
        stats = self.alex.get(f"{self.base}/cars/{self.car_id}/stats?year=2026").json()
        self.assertEqual((stats["km"], stats["years"], stats["consumption"]), (0, [], None))
        self.assertEqual(stats["members"], [])

    def test_unknown_car(self):
        self.assertEqual(self.alex.get(f"{self.base}/cars/9999/stats").status_code, 404)


if __name__ == "__main__":
    unittest.main()

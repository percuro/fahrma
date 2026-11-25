import unittest
from datetime import date

from tests.test_api import GroupSetupMixin


class ProfileTests(GroupSetupMixin, unittest.TestCase):
    def test_locale_set_and_reset(self):
        self.assertIsNone(self.alex.get("/v1/auth/me").json()["locale"])
        me = self.alex.patch("/v1/auth/me", json={"locale": "en"}).json()
        self.assertEqual(me["locale"], "en")
        # Changing only the name keeps the language
        me = self.alex.patch("/v1/auth/me", json={"display_name": "Alexandra"}).json()
        self.assertEqual((me["display_name"], me["locale"]), ("Alexandra", "en"))
        self.assertIsNone(self.alex.patch("/v1/auth/me", json={"locale": None}).json()["locale"])
        self.assertEqual(self.alex.patch("/v1/auth/me", json={"locale": "fr"}).status_code, 422)


class GroupSettingsTests(GroupSetupMixin, unittest.TestCase):
    def test_timezone_defaults_and_validation(self):
        group = self.alex.get(self.base).json()
        self.assertIsNone(group["timezone"])
        self.assertEqual(group["effective_timezone"], "UTC")
        self.assertEqual(group["today"], "2026-11-24")
        group = self.alex.patch(self.base, json={"timezone": "Europe/Berlin"}).json()
        self.assertEqual((group["timezone"], group["effective_timezone"]), ("Europe/Berlin", "Europe/Berlin"))
        response = self.alex.patch(self.base, json={"timezone": "Mars/Base"})
        self.assertEqual(response.json()["detail"]["code"], "timezone_invalid")
        self.assertIsNone(self.alex.patch(self.base, json={"timezone": None}).json()["timezone"])
        self.assertEqual(self.sam.patch(self.base, json={"timezone": "Europe/Berlin"}).status_code, 403)

    def test_currency_only_before_first_amount(self):
        self.assertEqual(self.alex.patch(self.base, json={"currency": "CHF"}).json()["currency"], "CHF")
        self.assertEqual(self.alex.patch(self.base, json={"currency": "chf"}).status_code, 422)
        self.fuel(self.alex, 5000, self.alex_id)
        response = self.alex.patch(self.base, json={"currency": "EUR"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "currency_locked")
        # Renaming still works and sending the same currency is not a change
        group = self.alex.patch(self.base, json={"name": "Renamed", "currency": "CHF"}).json()
        self.assertEqual((group["name"], group["currency"]), ("Renamed", "CHF"))

    def test_group_today_limits_the_settlement_date(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        self.fuel(self.alex, 1000, self.alex_id, day="2026-11-20")
        response = self.alex.post(f"{self.base}/settlements", json={"period_end": "2026-11-25"})
        self.assertEqual(response.json()["detail"]["code"], "period_end_future")
        self.assertEqual(
            self.alex.post(f"{self.base}/settlements", json={"period_end": date(2026, 11, 24).isoformat()}).status_code,
            201,
        )


class EnergyAndSingleEntryTests(GroupSetupMixin, unittest.TestCase):
    def test_electric_car_and_single_entries(self):
        car = self.alex.post(
            f"{self.base}/cars", json={"name": "EV", "start_odometer_km": 0, "energy_unit": "kWh"}
        ).json()
        self.assertEqual(car["energy_unit"], "kWh")
        invalid = {"name": "X", "start_odometer_km": 0, "energy_unit": "gal"}
        self.assertEqual(self.alex.post(f"{self.base}/cars", json=invalid).status_code, 422)
        fuel = self.alex.post(
            f"{self.base}/fuel",
            json={"car_id": car["id"], "date": "2026-11-20", "amount_cents": 1500, "paid_by_user_id": self.alex_id,
                  "quantity_milli": 42500},
        ).json()  # fmt: skip
        self.assertEqual(self.alex.get(f"{self.base}/fuel/{fuel['id']}").json()["quantity_milli"], 42500)
        trip = self.trip(self.alex, 10000, 10050, [(self.alex_id, 1)])
        self.assertEqual(self.sam.get(f"{self.base}/trips/{trip['id']}").json()["km"], 50)
        expense = self.alex.post(
            f"{self.base}/expenses",
            json={"date": "2026-11-20", "category": "wash", "amount_cents": 900, "paid_by_user_id": self.alex_id,
                  "allocation": "equal"},
        ).json()  # fmt: skip
        self.assertEqual(self.alex.get(f"{self.base}/expenses/{expense['id']}").json()["amount_cents"], 900)
        self.assertEqual(self.alex.get(f"{self.base}/trips/9999").json()["detail"]["code"], "trip_not_found")


if __name__ == "__main__":
    unittest.main()

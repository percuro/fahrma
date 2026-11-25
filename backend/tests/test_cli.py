"""Command-line tools for the instance: set_role and stats."""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from app.cli import set_role, stats
from tests.test_api import GroupSetupMixin


class CliTests(GroupSetupMixin, unittest.TestCase):
    def run_set_role(self, *args: str) -> str:
        output = io.StringIO()
        with (
            mock.patch("sys.argv", ["set_role", *args]),
            mock.patch.object(set_role, "SessionLocal", self.env.SessionLocal),
        ):
            with redirect_stdout(output):
                set_role.main()
        return output.getvalue()

    def test_set_role(self):
        self.assertIn("sam is now admin", self.run_set_role("sam", "admin"))
        self.assertEqual(self.sam.get("/v1/auth/me").json()["role"], "admin")

    def test_last_admin_cannot_be_demoted(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_set_role("alex", "user")
        self.assertIn("last active admin", str(raised.exception))

    def test_stats_have_numbers_only(self):
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        db = self.env.SessionLocal()
        try:
            data = stats.collect(db)
        finally:
            db.close()
        self.assertEqual((data["accounts"], data["admins"], data["groups"], data["trips"]), (2, 1, 1, 1))
        self.assertNotIn("Test group", repr(data))


if __name__ == "__main__":
    unittest.main()

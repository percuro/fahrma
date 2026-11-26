"""Deleting accounts unused for months (INACTIVE_DELETE_MONTHS), with a warning first."""

import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from app import config
from app.cli import inactive as inactive_cli
from app.models.group import Group
from app.models.user import User
from app.services import inactive_accounts
from app.services.auth_service import utcnow
from app.services.inactive_accounts import WARNING_DAYS, run_round, shift_months
from tests.migration_support import alembic
from tests.support import PASSWORD, ApiTestEnvironment, accept
from tests.test_accounts import code
from tests.test_mail import MailOutbox

NOW = datetime(2026, 11, 26, 12, 0)
MONTHS = 12
LONG_AGO = NOW - timedelta(days=400)


class ShiftMonthsTest(unittest.TestCase):
    def test_shift(self):
        self.assertEqual(shift_months(datetime(2026, 1, 31, 8), 1), datetime(2026, 2, 28, 8))
        self.assertEqual(shift_months(datetime(2028, 1, 31), 1), datetime(2028, 2, 29))
        self.assertEqual(shift_months(datetime(2026, 11, 26), 14), datetime(2028, 1, 26))
        self.assertEqual(shift_months(datetime(2026, 3, 31), -1), datetime(2026, 2, 28))
        self.assertEqual(shift_months(datetime(2026, 1, 15), -12), datetime(2025, 1, 15))


class SettingTest(unittest.TestCase):
    def months(self, value):
        with mock.patch.dict(os.environ, {"INACTIVE_DELETE_MONTHS": value}):
            return config.get_inactive_delete_months()

    def test_values(self):
        self.assertIsNone(self.months(""))
        self.assertIsNone(self.months("0"))
        self.assertEqual(self.months("24"), 24)
        for bad in ("2", "-1", "twelve", "1.5"):
            with self.subTest(value=bad), self.assertRaises(config.ConfigError):
                self.months(bad)


class InactiveTestCase(unittest.TestCase):
    """alex: instance admin; sam shares alex's group; kim has a group alone and an address."""

    def setUp(self):
        self.env = ApiTestEnvironment()
        self.addCleanup(self.env.close)
        self.env.create_user("alex", display_name="Alex", role="admin")
        self.alex = self.env.client("alex")
        group = self.alex.post("/v1/groups", json={"name": "Shared"}).json()
        self.shared = group["id"]
        invite = self.alex.post(f"/v1/groups/{self.shared}/invites").json()
        accept(self.env.client(None), invite["url"], username="sam", display_name="Sam", password=PASSWORD)
        self.env.create_user("kim", display_name="Kim")
        kim = self.env.client("kim")
        self.alone = kim.post("/v1/groups", json={"name": "Kim alone"}).json()["id"]
        kim.post(f"/v1/groups/{self.alone}/members", json={"display_name": "Grandma"})
        self.update("kim", email="kim@example.org", locale="de")
        # Everyone was active "now" unless a test says otherwise
        for name in ("alex", "sam", "kim"):
            self.update(name, last_seen_at=NOW, created_at=NOW - timedelta(days=800))

    def update(self, username, **values):
        with self.env.SessionLocal() as db:
            user = db.query(User).filter(User.username == username).one()
            for key, value in values.items():
                setattr(user, key, value)
            db.commit()

    def user(self, username_or_id):
        with self.env.SessionLocal() as db:
            if isinstance(username_or_id, int):
                return db.get(User, username_or_id)
            return db.query(User).filter(User.username == username_or_id).one_or_none()

    def user_id(self, username):
        return self.user(username).id

    def run_at(self, now, months=MONTHS, dry_run=False):
        with self.env.SessionLocal() as db:
            return run_round(db, now, months, dry_run=dry_run)

    def group_exists(self, group_id):
        with self.env.SessionLocal() as db:
            return db.get(Group, group_id) is not None


class RoundTests(InactiveTestCase):
    def test_active_accounts_are_left_alone(self):
        result = self.run_at(NOW)
        self.assertEqual((result.warned, result.deleted, result.exempt), (0, 0, 0))

    def test_warn_first_then_delete_after_the_grace_period(self):
        sam_id, kim_id = self.user_id("sam"), self.user_id("kim")
        for name in ("sam", "kim"):
            self.update(name, last_seen_at=LONG_AGO)
        with mock.patch.dict(os.environ, {"MAIL_FROM": "fahrma <noreply@example.org>", "MAIL_DIR": "/nonexistent"}):
            first = self.run_at(NOW)
        self.assertEqual((first.warned, first.warned_by_mail, first.deleted), (2, 1, 0))
        [mail] = first.mails
        due = (NOW + timedelta(days=WARNING_DAYS)).date()
        self.assertEqual(mail.to, "kim@example.org")
        self.assertIn(f"{due:%d.%m.%Y}", mail.subject)
        self.assertIn("http://localhost:5173", mail.body)
        self.assertIn("12 Monaten", mail.body)
        # Warned only once
        self.assertEqual(self.run_at(NOW + timedelta(days=1)).warned, 0)
        # Not before the grace period is over
        self.assertEqual(self.run_at(NOW + timedelta(days=WARNING_DAYS - 1)).deleted, 0)
        last = self.run_at(NOW + timedelta(days=WARNING_DAYS))
        self.assertEqual(last.deleted, 2)

        sam, kim = self.user(sam_id), self.user(kim_id)
        self.assertIsNotNone(sam.deleted_at)
        self.assertEqual((kim.email, kim.username, kim.inactivity_warned_at), (None, f"~deleted-{kim_id}", None))
        # Kim's group had nobody else (a person without an account does not count); the shared one stays
        self.assertFalse(self.group_exists(self.alone))
        self.assertTrue(self.group_exists(self.shared))
        members = {m["user_id"]: m for m in self.alex.get(f"/v1/groups/{self.shared}").json()["members"]}
        self.assertTrue(members[sam_id]["deleted"])

    def test_using_the_app_again_voids_the_warning(self):
        self.update("sam", last_seen_at=LONG_AGO)
        self.assertEqual(self.run_at(NOW).warned, 1)
        self.update("sam", last_seen_at=NOW + timedelta(days=3))
        result = self.run_at(NOW + timedelta(days=WARNING_DAYS + 1))
        self.assertEqual((result.warned, result.deleted), (0, 0))
        self.assertIsNone(self.user("sam").deleted_at)
        # A year later it starts over, with a new warning
        later = NOW + timedelta(days=3 + 366)
        self.update("kim", last_seen_at=later)  # only sam is unused that long
        self.assertEqual(self.run_at(later).warned, 1)
        self.assertEqual(self.run_at(later + timedelta(days=WARNING_DAYS)).deleted, 1)

    def test_warned_a_month_before_the_deadline(self):
        # Inactive for 11 months and a bit: warned now, deleted when the 12 months are over
        # (but never less than WARNING_DAYS after the warning)
        self.update("sam", last_seen_at=shift_months(NOW, -MONTHS) + timedelta(days=10))
        self.assertEqual(self.run_at(NOW - timedelta(days=21)).warned, 0)
        self.assertEqual(self.run_at(NOW).warned, 1)
        self.assertEqual(self.run_at(NOW + timedelta(days=29)).deleted, 0)
        self.assertEqual(self.run_at(NOW + timedelta(days=30)).deleted, 1)

    def test_never_logged_in_counts_from_creation(self):
        self.update("sam", last_seen_at=None, created_at=LONG_AGO)
        self.assertEqual(self.run_at(NOW).warned, 1)

    def test_admins_and_deactivated_accounts_are_kept(self):
        self.update("alex", last_seen_at=LONG_AGO)
        self.update("sam", last_seen_at=LONG_AGO, is_active=False)
        result = self.run_at(NOW + timedelta(days=WARNING_DAYS))
        result = self.run_at(NOW + timedelta(days=2 * WARNING_DAYS))
        self.assertEqual((result.warned, result.deleted, result.exempt), (0, 0, 2))
        self.assertIsNone(self.user("alex").deleted_at)
        self.assertIsNone(self.user("sam").inactivity_warned_at)

    def test_people_without_an_account_are_not_accounts(self):
        with self.env.SessionLocal() as db:
            db.query(User).filter(User.placeholder.is_(True)).update({"created_at": LONG_AGO})
            db.commit()
        self.assertEqual(self.run_at(NOW).warned, 0)

    def test_dry_run_changes_nothing(self):
        self.update("sam", last_seen_at=LONG_AGO)
        self.assertEqual(self.run_at(NOW, dry_run=True).warned, 1)
        self.assertIsNone(self.user("sam").inactivity_warned_at)
        self.run_at(NOW)
        result = self.run_at(NOW + timedelta(days=WARNING_DAYS), dry_run=True)
        self.assertEqual(result.deleted, 1)
        self.assertIsNone(self.user("sam").deleted_at)

    def test_scheduled_round_sends_the_warnings(self):
        outbox = MailOutbox()
        self.addCleanup(outbox.close)
        self.update("kim", last_seen_at=LONG_AGO)
        with mock.patch.dict(os.environ, {"INACTIVE_DELETE_MONTHS": "12"}):
            result = inactive_accounts.run_scheduled(self.env.SessionLocal)
        self.assertEqual(result.warned_by_mail, 1)
        message = outbox.last()
        self.assertEqual(message["To"], "kim@example.org")
        self.assertIn("gelöscht", message["Subject"])

    def test_scheduled_round_is_off_by_default(self):
        self.update("kim", last_seen_at=LONG_AGO)
        self.assertIsNone(inactive_accounts.run_scheduled(self.env.SessionLocal))
        self.assertIsNone(self.user("kim").inactivity_warned_at)


class VisibleTests(InactiveTestCase):
    def test_meta(self):
        self.assertIsNone(self.env.client(None).get("/v1/meta").json()["inactive_delete_months"])
        with mock.patch.dict(os.environ, {"INACTIVE_DELETE_MONTHS": "24"}):
            self.assertEqual(self.env.client(None).get("/v1/meta").json()["inactive_delete_months"], 24)

    def test_admins_see_when_a_warned_account_goes(self):
        self.update("sam", last_seen_at=LONG_AGO)
        with mock.patch.dict(os.environ, {"INACTIVE_DELETE_MONTHS": "12"}):
            self.run_at(utcnow())
            users = {u["username"]: u for u in self.alex.get("/v1/admin/users").json()}
        self.assertIsNotNone(users["sam"]["deletion_due"])
        self.assertIsNone(users["kim"]["deletion_due"])
        # Without the setting nothing is announced
        users = {u["username"]: u for u in self.alex.get("/v1/admin/users").json()}
        self.assertIsNone(users["sam"]["deletion_due"])


class DeletingFreesTheAddressTest(InactiveTestCase):
    def test_own_deletion_removes_the_address(self):
        kim_id = self.user_id("kim")
        kim = self.env.client("kim")
        response = kim.request("DELETE", "/v1/account", json={"password": PASSWORD})
        self.assertIn(response.status_code, (200, 204), response.text)
        self.assertIsNone(self.user(kim_id).email)
        # The address can belong to a new account
        self.env.create_user("kim2")
        self.update("kim2", email="kim@example.org")
        self.assertEqual(self.user("kim2").email, "kim@example.org")

    def test_admin_deletion_removes_the_address(self):
        kim_id = self.user_id("kim")
        self.assertEqual(self.alex.delete(f"/v1/admin/users/{kim_id}").status_code, 204)
        self.assertIsNone(self.user(kim_id).email)
        self.assertEqual(code(self.alex.delete(f"/v1/admin/users/{kim_id}"), 404), "account_not_found")


class CliTests(InactiveTestCase):
    def run_cli(self, *args, env=None):
        output = io.StringIO()
        with (
            mock.patch("sys.argv", ["inactive", *args]),
            mock.patch.object(inactive_cli, "SessionLocal", self.env.SessionLocal),
            mock.patch.dict(os.environ, env or {}),
            redirect_stdout(output),
        ):
            inactive_cli.main()
        return output.getvalue()

    def test_counts_without_changing(self):
        self.update("sam", last_seen_at=LONG_AGO)
        self.update("kim", last_seen_at=LONG_AGO - timedelta(days=4000))
        output = self.run_cli("--months", "12")
        self.assertRegex(output, r"would be warned now +2\n")
        self.assertIsNone(self.user("sam").inactivity_warned_at)

    def test_needs_a_setting(self):
        with self.assertRaises(SystemExit):
            self.run_cli()
        with self.assertRaises(SystemExit):
            self.run_cli("--run", "--months", "12")

    def test_run(self):
        self.update("sam", last_seen_at=LONG_AGO - timedelta(days=4000))
        output = self.run_cli("--run", env={"INACTIVE_DELETE_MONTHS": "12"})
        self.assertRegex(output, r"  warned now +1 \(0 by e-mail\)\n")
        self.assertIsNotNone(self.user("sam").inactivity_warned_at)


class MigrationTest(unittest.TestCase):
    def test_deleted_accounts_lose_their_address(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fahrma.db"
            alembic(path, "upgrade", "0008")
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                INSERT INTO users (username, display_name, password_hash, is_active, role, email, deleted_at,
                                   placeholder, created_at)
                VALUES ('kim', 'Kim', 'x', 1, 'user', 'kim@example.org', NULL, 0, '2026-01-01 10:00:00'),
                       ('~deleted-2', 'Gone', '!', 0, 'user', 'gone@example.org', '2026-05-01 10:00:00', 0,
                        '2026-01-01 10:00:00');
                """
            )
            connection.commit()
            connection.close()
            alembic(path, "upgrade", "head")
            connection = sqlite3.connect(path)
            try:
                rows = connection.execute("SELECT username, email, inactivity_warned_at FROM users ORDER BY id")
                self.assertEqual(rows.fetchall(), [("kim", "kim@example.org", None), ("~deleted-2", None, None)])
            finally:
                connection.close()
            alembic(path, "downgrade", "0008")


if __name__ == "__main__":
    unittest.main()

"""Upgrade a 0.3 database with accounts to the current schema, and back."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.migration_support import alembic


class AccountsMigrationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "fahrma.db"
        alembic(self.path, "upgrade", "0002")
        connection = sqlite3.connect(self.path)
        connection.executescript(
            """
            INSERT INTO users (username, display_name, password_hash, is_active, created_at) VALUES
              ('kim', 'Kim', 'x', 1, '2026-01-02 10:00:00'),
              ('alex', 'Alex', 'x', 1, '2026-01-01 10:00:00'),
              ('old', 'Old', 'x', 0, '2025-01-01 10:00:00');
            INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (1, 'hash', '2027-01-01 00:00:00');
            """
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.directory.cleanup()

    def query(self, sql: str) -> list[tuple]:
        connection = sqlite3.connect(self.path)
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def test_oldest_active_account_becomes_admin(self):
        alembic(self.path, "upgrade", "head")
        self.assertEqual(
            self.query("SELECT username, role, deleted_at FROM users ORDER BY id"),
            [("kim", "user", None), ("alex", "admin", None), ("old", "user", None)],
        )
        self.assertEqual(self.query("SELECT user_id, user_agent, last_seen_at FROM user_sessions"), [(1, None, None)])
        self.assertEqual(self.query("SELECT count(*) FROM invitations"), [(0,)])

    def test_downgrade_keeps_accounts(self):
        alembic(self.path, "upgrade", "head")
        alembic(self.path, "downgrade", "0002")
        self.assertEqual(self.query("SELECT username FROM users ORDER BY id"), [("kim",), ("alex",), ("old",)])
        self.assertEqual(self.query("SELECT count(*) FROM user_sessions"), [(1,)])


class ReceiptsMigrationTest(unittest.TestCase):
    """0010 adds the receipts table; deleting an entry deletes its photo rows."""

    def test_receipts_follow_their_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fahrma.db"
            alembic(path, "upgrade", "head")
            connection = sqlite3.connect(path)
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.executescript(
                    """
                    INSERT INTO users (id, username, display_name, password_hash, is_active, role)
                      VALUES (1, 'kim', 'Kim', 'x', 1, 'admin');
                    INSERT INTO groups (id, name, currency) VALUES (1, 'G', 'EUR');
                    INSERT INTO cars (id, group_id, name, start_odometer_km, archived) VALUES (1, 1, 'Car', 0, 0);
                    INSERT INTO fuel_entries (id, group_id, car_id, date, amount_cents, paid_by_user_id, full_tank,
                                              created_by) VALUES (1, 1, 1, '2026-11-20', 100, 1, 1, 1);
                    INSERT INTO receipts (group_id, fuel_id, file, content_type, bytes, width, height, created_by)
                      VALUES (1, 1, 'a.jpg', 'image/jpeg', 10, 1, 1, 1);
                    """
                )
                with self.assertRaises(sqlite3.IntegrityError):  # neither fuel entry nor expense
                    connection.execute(
                        "INSERT INTO receipts (group_id, file, content_type, bytes, width, height, created_by)"
                        " VALUES (1, 'b.jpg', 'image/jpeg', 10, 1, 1, 1)"
                    )
                connection.execute("DELETE FROM fuel_entries WHERE id = 1")
                self.assertEqual(connection.execute("SELECT count(*) FROM receipts").fetchone(), (0,))
                connection.commit()
            finally:
                connection.close()
            alembic(path, "downgrade", "0009")


class OidcMigrationTest(unittest.TestCase):
    """0011 adds linked identities and started logins; old sessions count as password logins."""

    def test_identities_and_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fahrma.db"
            alembic(path, "upgrade", "0010")
            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """
                    INSERT INTO users (id, username, display_name, password_hash, is_active, role)
                      VALUES (1, 'kim', 'Kim', 'x', 1, 'admin'), (2, 'lee', 'Lee', 'x', 1, 'user');
                    INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (1, 'h', '2030-01-01');
                    """
                )
                connection.commit()
            finally:
                connection.close()
            alembic(path, "upgrade", "head")
            connection = sqlite3.connect(path)
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                self.assertEqual(
                    connection.execute("SELECT auth_method, authenticated_at FROM user_sessions").fetchone(),
                    ("password", None),
                )
                connection.execute("INSERT INTO oidc_identities (user_id, issuer, subject) VALUES (1, 'i', 's')")
                with self.assertRaises(sqlite3.IntegrityError):  # one subject, one account
                    connection.execute("INSERT INTO oidc_identities (user_id, issuer, subject) VALUES (2, 'i', 's')")
                with self.assertRaises(sqlite3.IntegrityError):  # one link per account
                    connection.execute("INSERT INTO oidc_identities (user_id, issuer, subject) VALUES (1, 'i', 't')")
                connection.execute("DELETE FROM users WHERE id = 1")
                self.assertEqual(connection.execute("SELECT count(*) FROM oidc_identities").fetchone(), (0,))
                connection.commit()
            finally:
                connection.close()
            alembic(path, "downgrade", "0010")


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

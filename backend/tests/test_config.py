import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import config


class ConfigTest(unittest.TestCase):
    def env(self, **values):
        base = {
            "PUBLIC_URL": "",
            "CORS_ORIGINS": "",
            "COOKIE_SECURE": "",
            "CSRF_PROTECTION": "",
            "DEFAULT_TIMEZONE": "",
            "APP_TZ": "",
            "PUBLIC_APP_URL": "",
        }
        base.update(values)
        return mock.patch.dict(os.environ, base)

    def test_public_url_required(self):
        with self.env(), self.assertRaises(config.ConfigError):
            config.validate()

    def test_public_url_validation(self):
        for bad in ("cars.example.org", "ftp://x.org", "https://x.org/sub"):
            with self.env(PUBLIC_URL=bad), self.assertRaises(config.ConfigError):
                config.get_public_url()
        with self.env(PUBLIC_URL="https://cars.example.org/"):
            self.assertEqual(config.get_public_url(), "https://cars.example.org")

    def test_secure_defaults(self):
        with self.env(PUBLIC_URL="https://cars.example.org"):
            self.assertTrue(config.csrf_enabled())
            self.assertTrue(config.cookie_secure())
            self.assertEqual(config.get_allowed_origins(), ["https://cars.example.org"])
        with self.env(PUBLIC_URL="http://localhost:8000"):
            self.assertFalse(config.cookie_secure())
        with self.env(
            PUBLIC_URL="http://localhost:8000", COOKIE_SECURE="true", CORS_ORIGINS="http://a.test, http://b.test/"
        ):
            self.assertTrue(config.cookie_secure())
            self.assertEqual(config.get_allowed_origins(), ["http://localhost:8000", "http://a.test", "http://b.test"])

    def test_legacy_public_app_url(self):
        with self.env(PUBLIC_APP_URL="https://cars.example.org"):
            self.assertEqual(config.get_public_url(), "https://cars.example.org")
        with self.env(PUBLIC_URL="https://new.example.org", PUBLIC_APP_URL="https://old.example.org"):
            self.assertEqual(config.get_public_url(), "https://new.example.org")

    def test_timezone_default_alias_and_validation(self):
        with self.env():
            self.assertEqual(config.get_default_timezone_name(), "UTC")
        with self.env(APP_TZ="Europe/Berlin"):
            self.assertEqual(config.get_default_timezone_name(), "Europe/Berlin")
        with self.env(DEFAULT_TIMEZONE="America/New_York", APP_TZ="Europe/Berlin"):
            self.assertEqual(config.get_default_timezone_name(), "America/New_York")
        with self.env(PUBLIC_URL="https://x.org", DEFAULT_TIMEZONE="Mars/Base"), self.assertRaises(config.ConfigError):
            config.validate()

    def test_oidc_settings(self):
        with self.env(OIDC_ISSUER="", OIDC_CLIENT_ID=""):
            self.assertIsNone(config.get_oidc_settings())
        with self.env(OIDC_ISSUER="https://auth.example.org", OIDC_CLIENT_ID=""), self.assertRaises(config.ConfigError):
            config.get_oidc_settings()
        with self.env(OIDC_ISSUER="auth.example.org", OIDC_CLIENT_ID="x"), self.assertRaises(config.ConfigError):
            config.get_oidc_settings()
        env = {"OIDC_ISSUER": "https://auth.example.org", "OIDC_CLIENT_ID": "fahrma"}
        with self.env(**env, OIDC_SCOPES="profile email"), self.assertRaises(config.ConfigError):
            config.get_oidc_settings()
        with self.env(**env, OIDC_SCOPES="", OIDC_CLIENT_SECRET="", OIDC_LABEL="", OIDC_AUTO_CREATE=""):
            settings = config.get_oidc_settings()
        self.assertEqual(settings.scopes, "openid profile email")
        self.assertEqual((settings.client_secret, settings.auto_create), (None, False))

    def test_oidc_client_secret_file(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "secret"
            secret.write_text("geheim\n", encoding="utf-8")
            env = {"OIDC_ISSUER": "https://auth.example.org", "OIDC_CLIENT_ID": "fahrma", "OIDC_CLIENT_SECRET": "x"}
            with self.env(**env, OIDC_CLIENT_SECRET_FILE=str(secret)):
                self.assertEqual(config.get_oidc_settings().client_secret, "geheim")
            missing = str(secret) + "-missing"
            with self.env(**env, OIDC_CLIENT_SECRET_FILE=missing), self.assertRaises(config.ConfigError):
                config.get_oidc_settings()

    def test_invalid_switches_and_numbers_stop_the_start(self):
        """A typo must not silently turn a protection off or a limit back to its default."""
        cases = {
            "CSRF_PROTECTION": "ture",
            "COOKIE_SECURE": "ja",
            "API_DOCS": "enabled",
            "PASSWORD_LOGIN": "nein",
            "RECEIPTS": "maybe",
            "PUSH": "aus",
            "SESSION_IDLE_MINUTES": "30m",
            "SESSION_ABSOLUTE_HOURS": "0",
            "INVITE_EXPIRY_DAYS": "-1",
            "COOKIE_SAMESITE": "lox",
        }
        for name, value in cases.items():
            with self.subTest(name=name), self.env(PUBLIC_URL="https://cars.example.org", **{name: value}):
                with self.assertRaises(config.ConfigError) as caught:
                    config.validate()
                self.assertIn(name, str(caught.exception))

    def test_switch_spellings_and_empty_values(self):
        for value, expected in (("on", True), ("Yes", True), ("1", True), (" TRUE ", True)):
            with self.env(API_DOCS=value):
                self.assertIs(config.api_docs_enabled(), expected)
        for value in ("off", "No", "0", "false"):
            with self.env(CSRF_PROTECTION=value):
                self.assertFalse(config.csrf_enabled())
        with self.env(CSRF_PROTECTION="", SESSION_IDLE_MINUTES="", COOKIE_SAMESITE=""):
            self.assertTrue(config.csrf_enabled())
            self.assertEqual(config.get_session_idle_minutes(), 30 * 24 * 60)
            self.assertEqual(config.get_cookie_samesite(), "lax")
        with self.env(COOKIE_SAMESITE="Strict", SESSION_ABSOLUTE_HOURS="12"):
            self.assertEqual(config.get_cookie_samesite(), "strict")
            self.assertEqual(config.get_session_absolute_hours(), 12)
        with self.env(PUBLIC_URL="https://cars.example.org", PUSH="off"):
            self.assertIsNone(config.get_push_settings())


if __name__ == "__main__":
    unittest.main()

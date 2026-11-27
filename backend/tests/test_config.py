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


if __name__ == "__main__":
    unittest.main()

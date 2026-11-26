"""Test environment: in-memory SQLite, fixed clock, TestClients with logged-in users."""

import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.api.dependencies.clock import FixedClock, get_clock
from app.api.routers.auth import register_rate_limiter
from app.db.database import Base, configure_sqlite, get_db
from app.main import app
from app.repositories.auth_repository import AuthRepository
from app.services.auth_service import AuthService
from app.services.invitation_service import invitation_rate_limiter, reset_account_limiter, reset_ip_limiter
from app.services.login_rate_limiter import login_rate_limiter
from app.services.mail import account_mail_limiter

PASSWORD = "sicheres-passwort-123"
TEST_ORIGIN = "http://localhost:5173"
# Independent of the surrounding environment (e.g. docker compose run with production
# values): CSRF on, allowed origin = the test clients' origin, default time zone.
TEST_ENV = {
    "PUBLIC_URL": TEST_ORIGIN,
    "PUBLIC_APP_URL": "",
    "CSRF_PROTECTION": "true",
    "COOKIE_SECURE": "false",
    "CORS_ORIGINS": "",
    "DEFAULT_TIMEZONE": "",
    "APP_TZ": "",
    # E-mail off unless a test turns it on (MailOutbox)
    "MAIL_FROM": "",
    "SMTP_HOST": "",
    "MAIL_DIR": "",
    # Web Push on (its default), sending replaced in tests that look at it (PushOutbox)
    "PUSH": "",
    "PUSH_DIR": "",
    "VAPID_SUBJECT": "",
    "VAPID_PRIVATE_KEY_FILE": "",
    "PUSH_ALLOWED_HOSTS": "",
    # Hosting: no plans, no billing, operator API off unless a test sets them
    "MAX_GROUPS_PER_USER": "",
    "MAX_MEMBERS_PER_GROUP": "",
    "MAX_CARS_PER_GROUP": "",
    "MAX_RECEIPT_MB_PER_GROUP": "",
    # Receipt photos on (the default), stored in a temporary directory per test
    "RECEIPTS": "",
    "MAX_RECEIPT_KB": "",
    "PLANS_FILE": "",
    "BILLING_URL": "",
    "OPERATOR_TOKEN": "",
    "OPERATOR_TOKEN_FILE": "",
}
HEADERS = {"X-Carshare-CSRF": "1", "Origin": TEST_ORIGIN}


class ApiTestEnvironment:
    def __init__(self, today: date = date(2026, 11, 24)):
        self.today = today
        self._receipts = tempfile.TemporaryDirectory()
        self.receipts_dir = Path(self._receipts.name)
        self._env = mock.patch.dict("os.environ", {**TEST_ENV, "RECEIPTS_DIR": self._receipts.name})
        self._env.start()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        configure_sqlite(self.engine)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False)
        for limiter in (
            login_rate_limiter,
            invitation_rate_limiter,
            register_rate_limiter,
            reset_ip_limiter,
            reset_account_limiter,
            account_mail_limiter,
        ):
            limiter.reset()

        def _db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_clock] = lambda: FixedClock(self.today)

    def create_user(
        self, username: str = "alex", password: str = PASSWORD, display_name: str | None = None, role: str = "user"
    ):
        db = self.SessionLocal()
        try:
            return AuthService(AuthRepository(db)).create_user(username, password, display_name, role=role)
        finally:
            db.close()

    def client(self, username: str | None = "alex", password: str = PASSWORD) -> TestClient:
        client = TestClient(app, headers=HEADERS)
        if username:
            response = client.post("/v1/auth/login", json={"username": username, "password": password})
            assert response.status_code == 200, response.text
        return client

    def close(self):
        app.dependency_overrides.clear()
        self.engine.dispose()
        self._env.stop()
        self._receipts.cleanup()


def token_of(url: str) -> str:
    """The token of an invitation link (PUBLIC_URL/invite#<token>)."""
    assert "/invite#" in url, url
    return url.split("#", 1)[1]


def accept(client: TestClient, url: str, **fields):
    """Use an invitation link; without a session this creates the account given in fields."""
    return client.post("/v1/invites/accept", json={"token": token_of(url), **fields})


def jpeg(width: int = 1200, height: int = 1600, size: int = 2000) -> bytes:
    """A minimal JPEG of about ``size`` bytes: what fahrma checks (markers and frame size), no real picture."""
    size_bytes = height.to_bytes(2, "big") + width.to_bytes(2, "big")
    frame = b"\xff\xc0\x00\x11\x08" + size_bytes + b"\x03" + b"\x01\x11\x00" * 3
    head = b"\xff\xd8" + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    padding = b""
    remaining = size - len(head) - len(frame) - 2
    while remaining > 4:
        chunk = min(remaining - 4, 65000)
        padding += b"\xff\xfe" + (chunk + 2).to_bytes(2, "big") + b"x" * chunk
        remaining -= chunk + 4
    return head + padding + frame + b"\xff\xd9"


JPEG_HEADERS = {"Content-Type": "image/jpeg"}

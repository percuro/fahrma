"""Test environment: in-memory SQLite, fixed clock, TestClients with logged-in users."""

from datetime import date
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
from app.services.invitation_service import invitation_rate_limiter
from app.services.login_rate_limiter import login_rate_limiter

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
}
HEADERS = {"X-Carshare-CSRF": "1", "Origin": TEST_ORIGIN}


class ApiTestEnvironment:
    def __init__(self, today: date = date(2026, 11, 24)):
        self.today = today
        self._env = mock.patch.dict("os.environ", TEST_ENV)
        self._env.start()
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        configure_sqlite(self.engine)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False)
        for limiter in (login_rate_limiter, invitation_rate_limiter, register_rate_limiter):
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


def token_of(url: str) -> str:
    """The token of an invitation link (PUBLIC_URL/invite#<token>)."""
    assert "/invite#" in url, url
    return url.split("#", 1)[1]


def accept(client: TestClient, url: str, **fields):
    """Use an invitation link; without a session this creates the account given in fields."""
    return client.post("/v1/invites/accept", json={"token": token_of(url), **fields})

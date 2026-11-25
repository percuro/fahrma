import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response, status

from app.config import cookie_secure, env_positive_int
from app.errors import AppError
from app.models.user import ROLE_USER, User, UserSession
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import LoginRequest

SESSION_COOKIE_NAME = "carshare_session"
# Long sessions: the home-screen web app on iOS has its own cookie storage, and
# frequent logins would get in the way of a quick entry at the parking spot.
SESSION_IDLE_MINUTES = env_positive_int("SESSION_IDLE_MINUTES", 30 * 24 * 60)
SESSION_ABSOLUTE_HOURS = env_positive_int("SESSION_ABSOLUTE_HOURS", 90 * 24)
MIN_PASSWORD_LENGTH = 12
LAST_SEEN_INTERVAL = timedelta(minutes=5)
USER_AGENT_MAX_LENGTH = 255
# New accounts only; names created before 0.4 stay valid
USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,32}$")


def utcnow() -> datetime:
    # naive UTC, matching server_default=CURRENT_TIMESTAMP in SQLite
    return datetime.now(UTC).replace(tzinfo=None)


def cookie_settings() -> dict:
    same_site = os.getenv("COOKIE_SAMESITE", "lax").lower()
    if same_site not in {"lax", "strict", "none"}:
        same_site = "lax"
    return {
        "secure": cookie_secure(),
        "httponly": True,
        "samesite": same_site,
        "path": "/",
    }


class AccountError(ValueError):
    """Invalid account data; a ValueError so the CLI can print it, convertible for the API."""

    def __init__(self, code: str, message: str, status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT, **params):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.params = params

    def to_http(self) -> AppError:
        return AppError(self.status_code, self.code, str(self), **self.params)


def normalize_username(username: str) -> str:
    """Lower-case and check the name of a new account."""
    username = username.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise AccountError(
            "username_invalid",
            "Usernames have 3 to 32 characters: letters a-z, digits, dot, underscore or hyphen",
        )
    return username


def clear_session_cookie(response: Response) -> None:
    settings = cookie_settings()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path=settings["path"],
        secure=settings["secure"],
        httponly=settings["httponly"],
        samesite=settings["samesite"],
    )


class AuthService:
    def __init__(self, repository: AuthRepository):
        self.repository = repository

    def login(self, login_in: LoginRequest, request: Request, response: Response) -> User:
        user = self.repository.get_user_by_username(login_in.username)
        if user is None or not user.is_active or not self.verify_password(login_in.password, user.password_hash):
            raise AppError(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Wrong username or password")
        self.start_session(user, request, response)
        return user

    def start_session(self, user: User, request: Request, response: Response) -> UserSession:
        """Create a session for an already verified account and set the cookie."""
        now = utcnow()
        self.repository.delete_expired_sessions(now)
        raw_token = secrets.token_urlsafe(48)
        user_agent = request.headers.get("User-Agent", "")[:USER_AGENT_MAX_LENGTH] or None
        session = self.repository.create_session(
            user,
            self.hash_token(raw_token),
            now + timedelta(minutes=SESSION_IDLE_MINUTES),
            user_agent,
            now,
        )
        # Persistent cookie (max_age), otherwise iOS drops it when the web app is closed
        response.set_cookie(
            SESSION_COOKIE_NAME,
            raw_token,
            max_age=SESSION_ABSOLUTE_HOURS * 3600,
            **cookie_settings(),
        )
        return session

    def logout(self, request: Request, response: Response) -> None:
        raw_token = request.cookies.get(SESSION_COOKIE_NAME)
        if raw_token:
            session = self.repository.get_session(self.hash_token(raw_token))
            if session:
                self.repository.delete_session(session)
        clear_session_cookie(response)

    def current_session(self, request: Request) -> UserSession:
        raw_token = request.cookies.get(SESSION_COOKIE_NAME)
        if not raw_token:
            raise AppError(status.HTTP_401_UNAUTHORIZED, "not_authenticated", "Not logged in")
        session = self.repository.get_session(self.hash_token(raw_token))
        now = utcnow()
        absolute_expiry = session.created_at + timedelta(hours=SESSION_ABSOLUTE_HOURS) if session is not None else None
        if session is None or session.expires_at <= now or (absolute_expiry is not None and absolute_expiry <= now):
            if session is not None:
                self.repository.delete_session(session)
            raise AppError(status.HTTP_401_UNAUTHORIZED, "session_expired", "Session expired")
        if not session.user.is_active:
            # 401, so the app shows the login page; deactivating also deletes all sessions
            raise AppError(status.HTTP_401_UNAUTHORIZED, "account_disabled", "Account disabled")
        refreshed_expiry = min(now + timedelta(minutes=SESSION_IDLE_MINUTES), absolute_expiry)
        extend = refreshed_expiry > session.expires_at + timedelta(minutes=1)
        seen = session.last_seen_at is None or now - session.last_seen_at >= LAST_SEEN_INTERVAL
        if extend or seen:
            self.repository.touch_session(session, refreshed_expiry if extend else None, now if seen else None)
        return session

    def current_user(self, request: Request) -> User:
        return self.current_session(request).user

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str | None = None,
        role: str = ROLE_USER,
        locale: str | None = None,
        commit: bool = True,
    ) -> User:
        username = normalize_username(username)
        if self.repository.get_user_by_username(username) is not None:
            raise AccountError("username_taken", "Username already exists", status.HTTP_409_CONFLICT)
        self.check_password(password)
        name = (display_name or "").strip() or username
        user = User(
            username=username, display_name=name, password_hash=self.hash_password(password), role=role, locale=locale
        )
        return self.repository.add_user(user, commit=commit)

    def set_password(self, username: str, password: str) -> None:
        user = self.repository.get_user_by_username(username)
        if user is None or user.is_deleted or user.placeholder:
            raise AccountError("account_not_found", "Account not found", status.HTTP_404_NOT_FOUND)
        self.check_password(password)
        self.repository.set_password(user, self.hash_password(password))

    @staticmethod
    def check_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AccountError(
                "password_too_short",
                f"Password needs at least {MIN_PASSWORD_LENGTH} characters",
                min_length=MIN_PASSWORD_LENGTH,
            )

    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return (
            "scrypt$16384$8$1$"
            + base64.urlsafe_b64encode(salt).decode()
            + "$"
            + base64.urlsafe_b64encode(digest).decode()
        )

    @staticmethod
    def verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt_text, digest_text = encoded.split("$")
            if algorithm != "scrypt":
                return False
            salt = base64.urlsafe_b64decode(salt_text)
            expected = base64.urlsafe_b64decode(digest_text)
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(expected),
            )
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

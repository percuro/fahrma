"""Runtime configuration, read from environment variables.

Only PUBLIC_URL is required in production; everything else has a safe default.
See docs/configuration.md for the full reference.
"""

import logging
import os
from dataclasses import dataclass
from email.utils import parseaddr
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

APP_NAME = "fahrma"
# File names (CSV export); lowercase, no spaces
APP_SLUG = "fahrma"

logger = logging.getLogger(__name__)

# Deprecated names from 0.1, still accepted so existing installations keep working
_ALIASES = {"PUBLIC_URL": "PUBLIC_APP_URL", "DEFAULT_TIMEZONE": "APP_TZ"}
_warned: set[str] = set()


class ConfigError(RuntimeError):
    """Raised when the configuration cannot work; the message is shown to the operator."""


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    legacy = _ALIASES.get(name)
    if legacy:
        legacy_value = os.getenv(legacy, "").strip()
        if legacy_value:
            if legacy not in _warned:
                logger.warning("%s is deprecated, use %s instead", legacy, name)
                _warned.add(legacy)
            return legacy_value
    return default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:////data/carshare.db")


def get_public_url() -> str:
    """External base URL, e.g. https://cars.example.org (no path)."""
    value = _env("PUBLIC_URL").rstrip("/")
    if not value:
        raise ConfigError("PUBLIC_URL is not set, e.g. PUBLIC_URL=https://cars.example.org")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ConfigError(f"PUBLIC_URL must start with http:// or https:// (got {value!r})")
    if parts.path not in {"", "/"}:
        raise ConfigError("PUBLIC_URL must not contain a path; serving under a sub-path is not supported")
    return f"{parts.scheme}://{parts.netloc}"


def get_allowed_origins() -> list[str]:
    """Origins allowed for state-changing requests: PUBLIC_URL plus optional CORS_ORIGINS."""
    origins = [get_public_url()]
    extra = os.getenv("CORS_ORIGINS", "")
    origins += [origin.strip().rstrip("/") for origin in extra.split(",") if origin.strip()]
    return origins


def csrf_enabled() -> bool:
    return env_bool("CSRF_PROTECTION", True)


def cookie_secure() -> bool:
    """Secure cookies unless explicitly disabled; defaults to on for an https PUBLIC_URL."""
    if os.getenv("COOKIE_SECURE", "").strip():
        return env_bool("COOKIE_SECURE")
    return get_public_url().startswith("https://")


def api_docs_enabled() -> bool:
    return env_bool("API_DOCS")


def get_default_timezone_name() -> str:
    return _env("DEFAULT_TIMEZONE", "UTC")


@lru_cache
def get_zone(name: str) -> ZoneInfo:
    """ZoneInfo for an IANA name; raises ValueError for unknown names."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown time zone {name!r}") from exc


def is_valid_timezone(name: str) -> bool:
    try:
        get_zone(name)
    except ValueError:
        return False
    return True


def get_default_timezone() -> ZoneInfo:
    name = get_default_timezone_name()
    try:
        return get_zone(name)
    except ValueError as exc:
        raise ConfigError(f"Unknown time zone {name!r} in DEFAULT_TIMEZONE") from exc


REGISTRATION_MODES = ("invite", "open")


def get_registration_mode() -> str:
    """invite (default): accounts only through an invitation; open: anyone may register."""
    value = os.getenv("REGISTRATION", "").strip().lower() or "invite"
    if value not in REGISTRATION_MODES:
        raise ConfigError(f"REGISTRATION must be 'invite' or 'open' (got {value!r})")
    return value


def get_invite_expiry_days() -> int:
    return env_positive_int("INVITE_EXPIRY_DAYS", 7)


def _optional_url(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    if urlsplit(value).scheme not in {"http", "https"}:
        raise ConfigError(f"{name} must start with http:// or https:// (got {value!r})")
    return value


def get_operator_links() -> dict[str, str | None]:
    """Imprint, privacy policy and terms of the operator; shown in the app when set."""
    return {
        "imprint_url": _optional_url("IMPRINT_URL"),
        "privacy_url": _optional_url("PRIVACY_URL"),
        "terms_url": _optional_url("TERMS_URL"),
    }


LIMIT_NAMES = ("MAX_GROUPS_PER_USER", "MAX_MEMBERS_PER_GROUP", "MAX_CARS_PER_GROUP")


def get_limit(name: str) -> int | None:
    """A limit from the environment; empty or 0 = unlimited."""
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number (got {value!r})") from exc
    if number < 0:
        raise ConfigError(f"{name} must not be negative (got {value!r})")
    return number or None


SMTP_SECURITY_MODES = {"starttls": 587, "tls": 465, "none": 25}


@dataclass(frozen=True)
class MailSettings:
    sender: str
    host: str | None
    port: int
    security: str
    username: str | None
    password: str | None
    # Development and tests: write each mail as a .eml file here instead of sending it
    directory: Path | None


def get_mail_settings() -> MailSettings | None:
    """E-mail is optional: off unless MAIL_FROM and SMTP_HOST (or MAIL_DIR) are set."""
    sender = os.getenv("MAIL_FROM", "").strip()
    host = os.getenv("SMTP_HOST", "").strip() or None
    directory = os.getenv("MAIL_DIR", "").strip() or None
    if not sender and not host and not directory:
        return None
    if not sender:
        raise ConfigError("MAIL_FROM is not set, e.g. MAIL_FROM=fahrma <noreply@example.org>")
    if not host and not directory:
        raise ConfigError("MAIL_FROM is set but SMTP_HOST is not; set both to send e-mail")
    if "\n" in sender or "\r" in sender or "@" not in parseaddr(sender)[1]:
        raise ConfigError(f"MAIL_FROM is not an e-mail address (got {sender!r})")
    security = os.getenv("SMTP_SECURITY", "").strip().lower() or "starttls"
    if security not in SMTP_SECURITY_MODES:
        raise ConfigError(f"SMTP_SECURITY must be starttls, tls or none (got {security!r})")
    port_text = os.getenv("SMTP_PORT", "").strip()
    try:
        port = int(port_text) if port_text else SMTP_SECURITY_MODES[security]
    except ValueError as exc:
        raise ConfigError(f"SMTP_PORT must be a number (got {port_text!r})") from exc
    password = os.getenv("SMTP_PASSWORD", "") or None
    password_file = os.getenv("SMTP_PASSWORD_FILE", "").strip()
    if password_file:
        try:
            password = Path(password_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ConfigError(f"SMTP_PASSWORD_FILE cannot be read: {exc}") from exc
    return MailSettings(
        sender=sender,
        host=host,
        port=port,
        security=security,
        username=os.getenv("SMTP_USERNAME", "").strip() or None,
        password=password,
        directory=Path(directory) if directory else None,
    )


def mail_enabled() -> bool:
    return get_mail_settings() is not None


def validate() -> None:
    """Fail fast at startup with a readable message instead of on the first request."""
    get_public_url()
    get_default_timezone()
    get_registration_mode()
    get_operator_links()
    for name in LIMIT_NAMES:
        get_limit(name)
    get_mail_settings()

"""Runtime configuration, read from environment variables.

Only PUBLIC_URL is required in production; everything else has a safe default.
See docs/configuration.md for the full reference.
"""

import json
import logging
import os
import re
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


# Limits that belong to a group and therefore to its plan; MAX_GROUPS_PER_USER stays per instance
GROUP_LIMITS = {"members_per_group": "MAX_MEMBERS_PER_GROUP", "cars_per_group": "MAX_CARS_PER_GROUP"}
DEFAULT_PLAN_ID = "default"
_PLAN_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_LOCALE = re.compile(r"^[a-z]{2}$")


@dataclass(frozen=True)
class Plan:
    id: str
    # Shown to people; one text, or one per language ({"de": "Gratis", "en": "Free"})
    name: str | dict[str, str]
    # None = unlimited
    members_per_group: int | None
    cars_per_group: int | None

    def limit(self, name: str) -> int | None:
        return getattr(self, name)


@dataclass(frozen=True)
class PlanSettings:
    # In the order of the file: usually the smallest first
    plans: dict[str, Plan]
    # The plan of every group without its own (or whose own plan has run out)
    default: str
    # PLANS_FILE is set: plans are shown in the app; otherwise one implicit plan from MAX_*
    configured: bool

    @property
    def default_plan(self) -> Plan:
        return self.plans[self.default]


def _plan_limit(raw: dict, key: str, where: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"PLANS_FILE: {where}.{key} must be a whole number of at least 0 or null (got {value!r})")
    return value or None


def _plan_name(raw: dict, where: str) -> str | dict[str, str]:
    name = raw.get("name")
    if isinstance(name, str) and name.strip() and len(name) <= 40:
        return name.strip()
    if (
        isinstance(name, dict)
        and name
        and all(isinstance(k, str) and _LOCALE.match(k) for k in name)
        and all(isinstance(v, str) and v.strip() and len(v) <= 40 for v in name.values())
    ):
        return {k: v.strip() for k, v in name.items()}
    raise ConfigError(
        f'PLANS_FILE: {where}.name must be a text of up to 40 characters or {{"de": "…", "en": "…"}} (got {name!r})'
    )


def _parse_plans(text: str) -> PlanSettings:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ConfigError(f"PLANS_FILE is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) - {"default", "plans"}:
        raise ConfigError('PLANS_FILE must be an object with the keys "default" and "plans"')
    raw_plans = data.get("plans")
    if not isinstance(raw_plans, list) or not raw_plans:
        raise ConfigError('PLANS_FILE: "plans" must be a non-empty list')
    plans: dict[str, Plan] = {}
    allowed = {"id", "name", *GROUP_LIMITS}
    for index, raw in enumerate(raw_plans):
        where = f"plans[{index}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"PLANS_FILE: {where} must be an object")
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise ConfigError(f"PLANS_FILE: {where} has unknown keys {', '.join(unknown)}")
        plan_id = raw.get("id")
        if not isinstance(plan_id, str) or not _PLAN_ID.match(plan_id):
            raise ConfigError(f"PLANS_FILE: {where}.id must be 1-32 of a-z, 0-9, - and _ (got {plan_id!r})")
        if plan_id in plans:
            raise ConfigError(f"PLANS_FILE: the id {plan_id!r} appears twice")
        plans[plan_id] = Plan(
            id=plan_id,
            name=_plan_name(raw, where),
            members_per_group=_plan_limit(raw, "members_per_group", where),
            cars_per_group=_plan_limit(raw, "cars_per_group", where),
        )
    default = data.get("default")
    if default not in plans:
        raise ConfigError(f'PLANS_FILE: "default" must be the id of one of the plans (got {default!r})')
    return PlanSettings(plans=plans, default=default, configured=True)


@lru_cache(maxsize=4)
def _read_plans(path: str, modified: int) -> PlanSettings:
    """Cached per file and modification time: editing the file takes effect without a restart."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"PLANS_FILE cannot be read: {exc}") from exc
    return _parse_plans(text)


# The last valid content per PLANS_FILE: a file broken while running does not break the app
_last_good_plans: dict[str, PlanSettings] = {}
_reported_plan_errors: set[str] = set()


def get_plans(strict: bool = False) -> PlanSettings:
    """The plans a group can have. Without PLANS_FILE there is one plan with the MAX_* limits.

    If the file becomes invalid while running, the last valid content stays in force and the
    error is logged; ``strict`` (at startup) raises instead.
    """
    path = os.getenv("PLANS_FILE", "").strip()
    if not path:
        return PlanSettings(
            plans={
                DEFAULT_PLAN_ID: Plan(
                    id=DEFAULT_PLAN_ID,
                    name=DEFAULT_PLAN_ID,
                    members_per_group=get_limit("MAX_MEMBERS_PER_GROUP"),
                    cars_per_group=get_limit("MAX_CARS_PER_GROUP"),
                )
            },
            default=DEFAULT_PLAN_ID,
            configured=False,
        )
    both = [name for name in GROUP_LIMITS.values() if os.getenv(name, "").strip()]
    if both:
        raise ConfigError(f"Set the limits per plan in PLANS_FILE instead of {', '.join(both)}")
    try:
        try:
            modified = os.stat(path).st_mtime_ns
        except OSError as exc:
            raise ConfigError(f"PLANS_FILE cannot be read: {exc}") from exc
        settings = _read_plans(path, modified)
    except ConfigError as exc:
        last_good = _last_good_plans.get(path)
        if strict or last_good is None:
            raise
        if str(exc) not in _reported_plan_errors:
            _reported_plan_errors.add(str(exc))
            logger.error("%s – keeping the plans read before", exc)
        return last_good
    _last_good_plans[path] = settings
    _reported_plan_errors.clear()
    return settings


def get_billing_url() -> str | None:
    """Where group admins go to change their group's plan (a pricing page or a billing service)."""
    value = _optional_url("BILLING_URL")
    if value and "#" in value:
        raise ConfigError("BILLING_URL must not contain a fragment (#); fahrma adds one")
    return value


def get_operator_token() -> str | None:
    """Bearer token of the operator API (and key of the billing links); None = operator API off."""
    token = os.getenv("OPERATOR_TOKEN", "").strip() or None
    token_file = os.getenv("OPERATOR_TOKEN_FILE", "").strip()
    if token_file:
        try:
            token = Path(token_file).read_text(encoding="utf-8").strip() or None
        except OSError as exc:
            raise ConfigError(f"OPERATOR_TOKEN_FILE cannot be read: {exc}") from exc
    if token is not None and len(token) < 32:
        raise ConfigError("OPERATOR_TOKEN must be at least 32 characters long, e.g. from `openssl rand -hex 32`")
    return token


MIN_INACTIVE_DELETE_MONTHS = 3


def get_inactive_delete_months() -> int | None:
    """Delete accounts after this many months without a login (with a warning first); None = never."""
    value = os.getenv("INACTIVE_DELETE_MONTHS", "").strip()
    if not value or value == "0":
        return None
    try:
        months = int(value)
    except ValueError as exc:
        raise ConfigError(f"INACTIVE_DELETE_MONTHS must be a whole number (got {value!r})") from exc
    if months < MIN_INACTIVE_DELETE_MONTHS:
        raise ConfigError(
            f"INACTIVE_DELETE_MONTHS must be at least {MIN_INACTIVE_DELETE_MONTHS} or 0 for never (got {value!r})"
        )
    return months


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


# Hosts of the browsers' push services; the server only ever sends to these (no requests to
# arbitrary URLs a client hands in). PUSH_ALLOWED_HOSTS adds more, comma-separated.
PUSH_HOSTS = (
    "fcm.googleapis.com",  # Chrome, Edge on Android, Samsung Internet, Brave, Opera
    "push.services.mozilla.com",  # Firefox
    "push.apple.com",  # Safari on macOS, iOS and iPadOS (web.push.apple.com)
    "notify.windows.com",  # Edge on Windows (*.notify.windows.com)
)


@dataclass(frozen=True)
class PushSettings:
    # "mailto:…" or "https://…": how push services can reach the operator (VAPID "sub")
    subject: str
    # PEM file with the VAPID private key; None = generated once and kept in the database
    key_file: Path | None
    allowed_hosts: tuple[str, ...]
    # Development and tests: write each notification as a .json file here instead of sending it
    directory: Path | None


def get_push_settings() -> PushSettings | None:
    """Web Push is on by default (it needs no external account); PUSH=off turns it off."""
    if os.getenv("PUSH", "").strip().lower() in {"0", "false", "no", "off"}:
        return None
    subject = os.getenv("VAPID_SUBJECT", "").strip() or get_public_url()
    if not subject.startswith(("mailto:", "https://", "http://")):
        raise ConfigError(f"VAPID_SUBJECT must start with mailto: or https:// (got {subject!r})")
    key_file = os.getenv("VAPID_PRIVATE_KEY_FILE", "").strip()
    if key_file and not Path(key_file).is_file():
        raise ConfigError(f"VAPID_PRIVATE_KEY_FILE cannot be read: {key_file}")
    extra = os.getenv("PUSH_ALLOWED_HOSTS", "")
    hosts = PUSH_HOSTS + tuple(host.strip().lower() for host in extra.split(",") if host.strip())
    directory = os.getenv("PUSH_DIR", "").strip()
    return PushSettings(
        subject=subject,
        key_file=Path(key_file) if key_file else None,
        allowed_hosts=hosts,
        directory=Path(directory) if directory else None,
    )


def push_enabled() -> bool:
    return get_push_settings() is not None


def validate() -> None:
    """Fail fast at startup with a readable message instead of on the first request."""
    get_public_url()
    get_default_timezone()
    get_registration_mode()
    get_operator_links()
    for name in LIMIT_NAMES:
        get_limit(name)
    get_plans(strict=True)
    get_billing_url()
    get_operator_token()
    get_inactive_delete_months()
    get_mail_settings()
    get_push_settings()

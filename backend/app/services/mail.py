"""Sending e-mail (optional; see config.get_mail_settings).

Mails are plain text in the recipient's language, without images, tracking or HTML. They
are sent after the response (FastAPI background task), so a slow or broken mail server
never delays a request, and the response time does not tell whether an address exists.
A failure is logged; the link in a mail is always also available another way (shown to
the admin who created it, or requested again).
"""

import logging
import secrets
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from fastapi import BackgroundTasks, status

from app.config import MailSettings, get_mail_settings
from app.errors import AppError
from app.services.login_rate_limiter import LoginRateLimiter

logger = logging.getLogger(__name__)
SMTP_TIMEOUT_SECONDS = 20

# Mails an account can trigger (invitations, address confirmation): 20 per hour
account_mail_limiter = LoginRateLimiter(window_seconds=60 * 60)
account_mail_limiter.account_limit = 20
account_mail_limiter.ip_limit = 60


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


def require_mail() -> MailSettings:
    settings = get_mail_settings()
    if settings is None:
        raise AppError(status.HTTP_409_CONFLICT, "mail_disabled", "E-mail is not set up on this instance")
    return settings


def check_account_quota(user_id: int, ip_address: str) -> None:
    """Before an account sends a mail to someone; counts the attempt."""
    key = f"user-{user_id}"
    account_mail_limiter.check(key, ip_address)
    account_mail_limiter.record_failure(key, ip_address)


def build(settings: MailSettings, mail: Mail) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = mail.to
    message["Subject"] = mail.subject
    message["Date"] = formatdate(localtime=False, usegmt=True)
    domain = parseaddr(settings.sender)[1].rsplit("@", 1)[-1]
    message["Message-ID"] = make_msgid(domain=domain)
    # Tells mail servers and autoresponders that no human wrote it (RFC 3834)
    message["Auto-Submitted"] = "auto-generated"
    # Quoted-printable: 7-bit safe for every mail server, still readable as source
    message.set_content(mail.body, cte="quoted-printable")
    return message


def deliver(mail: Mail) -> None:
    """Send now; never raises (runs after the response)."""
    settings = get_mail_settings()
    if settings is None:
        return
    try:
        message = build(settings, mail)
        if settings.directory is not None:
            settings.directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
            path = settings.directory / f"{stamp}-{secrets.token_hex(4)}.eml"
            path.write_bytes(bytes(message))
            return
        context = ssl.create_default_context()
        if settings.security == "tls":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.host, settings.port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            )
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=SMTP_TIMEOUT_SECONDS)
        with client:
            if settings.security == "starttls":
                client.starttls(context=context)
            if settings.username:
                client.login(settings.username, settings.password or "")
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # The address stays out of the log; the reason is enough to fix the setup
        logger.error("Sending an e-mail failed: %s", exc)


def send_later(background: BackgroundTasks, mail: Mail) -> None:
    background.add_task(deliver, mail)

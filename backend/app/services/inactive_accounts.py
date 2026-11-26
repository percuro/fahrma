"""Deleting accounts nobody uses any more (INACTIVE_DELETE_MONTHS, off by default).

An operator who hosts fahrma for others must not keep personal data forever. With the
setting, an account that has not been used for that many months is deleted the same way
as when its owner deletes it (bookings stay anonymously in shared groups, groups without
other members go). Before that:

- The account is warned at least WARNING_DAYS ahead, by e-mail if it has a confirmed
  address. Using the app again in between makes the warning void (last_seen_at is newer).
- Accounts without an address cannot be warned; they still get the same grace period
  after the moment they would have been warned, so switching the setting on never deletes
  anything on the same day.
- Instance admins and accounts an admin deactivated are never deleted automatically: the
  former keep the instance manageable, the latter are the admins' decision.

The rounds run inside the app (app.web), once an hour; `python -m app.cli.inactive` shows
what a round would do.
"""

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_inactive_delete_months, mail_enabled
from app.models.user import ROLE_ADMIN, User
from app.services import mail_texts
from app.services.account_service import AccountService
from app.services.auth_service import utcnow
from app.services.mail import Mail, deliver

logger = logging.getLogger(__name__)

WARNING_DAYS = 30


def shift_months(moment: datetime, months: int) -> datetime:
    """The same day and time ``months`` later (or earlier); the 31st becomes the month's last day."""
    index = moment.year * 12 + moment.month - 1 + months
    year, month = divmod(index, 12)
    day = min(moment.day, calendar.monthrange(year, month + 1)[1])
    return moment.replace(year=year, month=month + 1, day=day)


def last_active(user: User) -> datetime:
    return max(user.last_seen_at or user.created_at, user.created_at)


def warning_is_valid(user: User) -> bool:
    return user.inactivity_warned_at is not None and user.inactivity_warned_at >= last_active(user)


def deletion_date(user: User, months: int) -> datetime | None:
    """When a warned account will be deleted; None if it has no valid warning."""
    if not warning_is_valid(user):
        return None
    return max(shift_months(last_active(user), months), user.inactivity_warned_at + timedelta(days=WARNING_DAYS))


@dataclass
class Round:
    warned: int = 0
    warned_by_mail: int = 0
    deleted: int = 0
    # Inactive long enough, but kept: instance admins and deactivated accounts
    exempt: int = 0
    mails: list[Mail] = field(default_factory=list)


def _candidates(db: Session, now: datetime, months: int):
    """Accounts that are due for a warning or a deletion (not yet deleted, not placeholders)."""
    cutoff = shift_months(now + timedelta(days=WARNING_DAYS), -months)
    seen = func.coalesce(User.last_seen_at, User.created_at)
    return db.scalars(
        select(User).where(User.deleted_at.is_(None), User.placeholder.is_(False), seen <= cutoff).order_by(User.id)
    ).all()


def run_round(db: Session, now: datetime, months: int, dry_run: bool = False) -> Round:
    """Warn and delete what is due at ``now`` (naive UTC). Mails are collected, not sent."""
    result = Round()
    send_mail = mail_enabled()
    for user in _candidates(db, now, months):
        if user.role == ROLE_ADMIN or not user.is_active:
            result.exempt += 1
            continue
        if not warning_is_valid(user):
            result.warned += 1
            if dry_run:
                continue
            user.inactivity_warned_at = now
            if send_mail and user.email:
                result.warned_by_mail += 1
                result.mails.append(_warning_mail(user, months, deletion_date(user, months)))
            continue
        due = deletion_date(user, months)
        if due is not None and now >= due:
            if dry_run:
                result.deleted += 1
                continue
            db.commit()  # keep the warnings of this round, whatever the deletion does
            try:
                AccountService(db).delete(user)
            except Exception:
                db.rollback()
                logger.exception("Deleting inactive account %d failed", user.id)
                continue
            result.deleted += 1
    if not dry_run:
        db.commit()
    return result


def _warning_mail(user: User, months: int, due: datetime) -> Mail:
    locale = mail_texts.pick_locale(user.locale)
    return mail_texts.inactive_warning(user.email, locale, user.username, months, last_active(user).date(), due.date())


def run_scheduled(session_factory) -> Round | None:
    """One round with its own session; sends the warnings after the changes are stored."""
    months = get_inactive_delete_months()
    if months is None:
        return None
    with session_factory() as db:
        result = run_round(db, utcnow(), months)
    for mail in result.mails:
        deliver(mail)
    if result.warned or result.deleted:
        logger.info(
            "Inactive accounts: %d warned (%d by e-mail), %d deleted",
            result.warned,
            result.warned_by_mail,
            result.deleted,
        )
    return result


def deletion_day(user: User) -> date | None:
    """For the administration page: the day a warned account will be deleted."""
    months = get_inactive_delete_months()
    if months is None or user.role == ROLE_ADMIN or not user.is_active:
        return None
    due = deletion_date(user, months)
    return due.date() if due else None

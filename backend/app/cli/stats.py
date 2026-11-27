"""Numbers about the instance, without any content (no names, no amounts).

docker compose exec app python -m app.cli.stats
"""

import argparse
import json
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.car import Car
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import Group, Membership
from app.models.receipt import Receipt
from app.models.security_event import SecurityEvent
from app.models.trip import Trip
from app.models.user import NO_PASSWORD, OidcIdentity, User
from app.services.auth_service import utcnow
from app.services.plans import effective_plan
from app.services.security_log import FAILURE_EVENTS


def _count(db: Session, query) -> int:
    return db.scalar(query) or 0


def collect(db: Session) -> dict:
    now = utcnow()
    accounts = select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.placeholder.is_(False))
    months: dict[str, int] = {}
    for model in (Trip, FuelEntry, Expense):
        month = func.strftime("%Y-%m", model.created_at)
        for key, count in db.execute(
            select(month, func.count()).where(model.created_at >= now - timedelta(days=366)).group_by(month)
        ):
            months[key] = months.get(key, 0) + count
    events = select(func.count()).select_from(SecurityEvent).where(SecurityEvent.created_at >= now - timedelta(days=1))
    plans: dict[str, int] = {}
    for group in db.scalars(select(Group)):
        plan = effective_plan(group).id
        plans[plan] = plans.get(plan, 0) + 1
    return {
        "accounts": _count(db, accounts),
        "accounts_active": _count(db, accounts.where(User.is_active.is_(True))),
        "accounts_seen_30_days": _count(db, accounts.where(User.last_seen_at >= now - timedelta(days=30))),
        "admins": _count(db, accounts.where(User.role == "admin", User.is_active.is_(True))),
        "people_without_account": _count(db, select(func.count()).select_from(User).where(User.placeholder.is_(True))),
        # Since 0.11: accounts linked to the OIDC provider, and those that can only log in there
        "accounts_oidc_linked": _count(db, select(func.count()).select_from(OidcIdentity)),
        "accounts_without_password": _count(
            db, accounts.where(User.password_hash == NO_PASSWORD, User.is_active.is_(True))
        ),
        "accounts_deleted": _count(db, select(func.count()).select_from(User).where(User.deleted_at.is_not(None))),
        "accounts_warned_inactive": _count(
            db,
            accounts.where(User.inactivity_warned_at.is_not(None), User.inactivity_warned_at >= User.last_seen_at),
        ),
        "groups": _count(db, select(func.count()).select_from(Group)),
        "memberships_active": _count(
            db, select(func.count()).select_from(Membership).where(Membership.active.is_(True))
        ),
        "cars": _count(db, select(func.count()).select_from(Car).where(Car.archived.is_(False))),
        "trips": _count(db, select(func.count()).select_from(Trip)),
        "fuel_entries": _count(db, select(func.count()).select_from(FuelEntry)),
        "expenses": _count(db, select(func.count()).select_from(Expense)),
        "receipts": _count(db, select(func.count()).select_from(Receipt)),
        "receipt_mb": round(_count(db, select(func.sum(Receipt.bytes))) / (1024 * 1024), 1),
        "entries_per_month": dict(sorted(months.items())),
        # Plan in force per group (one implicit plan "default" without PLANS_FILE)
        "groups_per_plan": dict(sorted(plans.items())),
        # Since 0.12: from the security log
        "logins_24_hours": _count(db, events.where(SecurityEvent.event == "auth.login")),
        "failed_attempts_24_hours": _count(db, events.where(SecurityEvent.event.in_(FAILURE_EVENTS))),
        "blocks_24_hours": _count(db, events.where(SecurityEvent.event == "auth.rate_limited")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Instance statistics without content")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        data = collect(db)
    finally:
        db.close()
    if args.json:
        print(json.dumps(data, indent=2))
        return
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for name, count in value.items():
                print(f"  {name}  {count}")
        else:
            print(f"{key:<24} {value}")


if __name__ == "__main__":
    main()

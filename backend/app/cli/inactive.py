"""Deleting inactive accounts (INACTIVE_DELETE_MONTHS): what a round would do, or run one now.

docker compose exec app python -m app.cli.inactive              # only count, change nothing
docker compose exec app python -m app.cli.inactive --months 24  # as if set to 24 months
docker compose exec app python -m app.cli.inactive --run        # warn and delete what is due now

The app runs these rounds by itself once an hour; --run is for trying it out.
"""

import argparse
import sys

from app.config import get_inactive_delete_months
from app.db.database import SessionLocal
from app.services import inactive_accounts
from app.services.auth_service import utcnow
from app.services.mail import deliver


def main() -> None:
    parser = argparse.ArgumentParser(description="Warn and delete accounts unused for months")
    parser.add_argument("--months", type=int, help="months without a login (default: INACTIVE_DELETE_MONTHS)")
    parser.add_argument("--run", action="store_true", help="really warn and delete (default: only count)")
    args = parser.parse_args()
    months = args.months or get_inactive_delete_months()
    if months is None:
        sys.exit("INACTIVE_DELETE_MONTHS is not set; pass --months to see what a setting would do")
    if args.run and args.months and args.months != get_inactive_delete_months():
        sys.exit("--run uses INACTIVE_DELETE_MONTHS; set it instead of --months")
    with SessionLocal() as db:
        result = inactive_accounts.run_round(db, utcnow(), months, dry_run=not args.run)
    for mail in result.mails:
        deliver(mail)
    verb = "" if args.run else "would be "
    by_mail = f" ({result.warned_by_mail} by e-mail)" if args.run else ""
    print(f"Accounts unused for {months} months, with {inactive_accounts.WARNING_DAYS} days warning:")
    for label, count in (
        (f"{verb}warned now", f"{result.warned}{by_mail}"),
        (f"{verb}deleted now", result.deleted),
        ("kept (admins, deactivated)", result.exempt),
    ):
        print(f"  {label:<28} {count}")


if __name__ == "__main__":
    main()

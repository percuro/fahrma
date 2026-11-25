"""Emergency exit: give an account the admin role (or take it away) from the command line.

docker compose exec app python -m app.cli.set_role <username> admin
"""

import argparse

from app.db.database import SessionLocal
from app.models.user import ROLE_USER, ROLES
from app.repositories.auth_repository import AuthRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Set the instance role of an account")
    parser.add_argument("username")
    parser.add_argument("role", choices=ROLES)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        repository = AuthRepository(db)
        user = repository.get_user_by_username(args.username)
        if user is None or user.is_deleted:
            raise SystemExit(f"Account {args.username!r} not found")
        if args.role == ROLE_USER and user.is_admin and repository.count_active_admins(exclude_user_id=user.id) == 0:
            raise SystemExit("This is the last active admin; make another account admin first")
        user.role = args.role
        db.commit()
        print(f"{user.username} is now {args.role}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

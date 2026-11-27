"""Instance administration: accounts and invitations. Admins never see group contents."""

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models.group import Membership
from app.models.user import ROLE_USER, User
from app.repositories.auth_repository import AuthRepository
from app.schemas.admin import AdminUserRead, AdminUserUpdate
from app.services.account_service import AccountService
from app.services.inactive_accounts import deletion_day


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AuthRepository(db)
        self.accounts = AccountService(db)

    def list_users(self) -> list[AdminUserRead]:
        counts = dict(
            self.db.execute(
                select(Membership.user_id, func.count()).where(Membership.active.is_(True)).group_by(Membership.user_id)
            ).all()
        )
        users = self.db.scalars(
            select(User).where(User.deleted_at.is_(None), User.placeholder.is_(False)).order_by(User.username)
        )
        return [self._read(user, counts.get(user.id, 0)) for user in users]

    def get_user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None or user.is_deleted or user.placeholder:
            raise AppError(status.HTTP_404_NOT_FOUND, "account_not_found", "Account not found")
        return user

    def update_user(self, admin: User, user_id: int, data: AdminUserUpdate) -> AdminUserRead:
        user = self.get_user(user_id)
        demote = data.role == ROLE_USER and user.is_admin
        deactivate = data.is_active is False and user.is_active
        if deactivate and user.id == admin.id:
            raise AppError(status.HTTP_409_CONFLICT, "self_deactivate", "You cannot deactivate your own account")
        if demote or deactivate:
            self.accounts.ensure_not_last_admin(user)
        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        self.db.commit()
        if deactivate:
            # Logged out everywhere at once
            self.repository.delete_sessions(user.id)
        self.db.refresh(user)
        return self._read(user, self._group_count(user.id))

    def delete_user(self, admin: User, user_id: int) -> None:
        user = self.get_user(user_id)
        if user.id == admin.id:
            # Deleting yourself needs your password: use DELETE /account
            raise AppError(status.HTTP_409_CONFLICT, "self_delete", "Delete your own account on the profile page")
        self.accounts.delete(user)

    def _group_count(self, user_id: int) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.user_id == user_id, Membership.active.is_(True))
            )
            or 0
        )

    @staticmethod
    def _read(user: User, group_count: int) -> AdminUserRead:
        return AdminUserRead(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_seen_at=user.last_seen_at,
            group_count=group_count,
            deletion_due=deletion_day(user),
            has_password=user.has_password,
            oidc_linked=user.oidc_linked,
        )

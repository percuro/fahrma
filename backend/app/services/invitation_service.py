"""One-time links: into a group, to create an account, or to set a new password.

Every link is PUBLIC_URL/invite#<token>. The token sits in the URL fragment, so it never
reaches server logs or Referer headers; the web app reads it and sends it in the body.
Only its SHA-256 hash is stored. Using a link is atomic: the first request that marks it
as used wins, a second one finds it invalid.
"""

import secrets
from datetime import datetime, timedelta

from fastapi import Request, Response, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_invite_expiry_days, get_public_url
from app.errors import AppError
from app.models.group import ROLE_MEMBER, Invite, Membership
from app.models.invitation import PURPOSE_PASSWORD_RESET, PURPOSE_SIGNUP, Invitation
from app.models.user import User, UserSession
from app.repositories.auth_repository import AuthRepository
from app.schemas.invitation import (
    InvitationAccept,
    InvitationAccepted,
    InvitationCreated,
    InvitationInfo,
    InvitationRead,
)
from app.services.auth_service import AccountError, AuthService, normalize_username, utcnow
from app.services.limits import check_new_group, check_new_member
from app.services.login_rate_limiter import LoginRateLimiter

RESET_EXPIRY = timedelta(hours=24)
# Used and expired links are kept a while for reference, then removed
KEEP_FINISHED = timedelta(days=30)
# Wrong tokens per IP address, like the login limit
invitation_rate_limiter = LoginRateLimiter()


def invalid() -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, "invite_invalid", "This link is invalid, expired or already used")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class InvitationService:
    def __init__(self, db: Session):
        self.db = db
        self.auth = AuthService(AuthRepository(db))

    # --- Instance admin -----------------------------------------------------

    def create_signup(self, admin: User, role: str, note: str | None) -> InvitationCreated:
        now = utcnow()
        return self._create(
            Invitation(
                purpose=PURPOSE_SIGNUP,
                role=role,
                note=note,
                created_by_user_id=admin.id,
                expires_at=now + timedelta(days=get_invite_expiry_days()),
            ),
            now,
        )

    def create_password_reset(self, admin: User, target: User) -> InvitationCreated:
        if not target.is_active:
            raise AppError(status.HTTP_409_CONFLICT, "account_inactive", "Reactivate the account first")
        now = utcnow()
        # Only the newest reset link for an account works
        self.db.execute(
            delete(Invitation).where(
                Invitation.purpose == PURPOSE_PASSWORD_RESET,
                Invitation.target_user_id == target.id,
                Invitation.used_at.is_(None),
            )
        )
        return self._create(
            Invitation(
                purpose=PURPOSE_PASSWORD_RESET,
                target_user_id=target.id,
                created_by_user_id=admin.id,
                expires_at=now + RESET_EXPIRY,
            ),
            now,
        )

    def _create(self, invitation: Invitation, now: datetime) -> InvitationCreated:
        self.db.execute(
            delete(Invitation).where(
                or_(Invitation.used_at.is_not(None), Invitation.expires_at <= now),
                Invitation.expires_at <= now - KEEP_FINISHED,
            )
        )
        token = secrets.token_urlsafe(32)
        invitation.token_hash = AuthService.hash_token(token)
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        return InvitationCreated(
            id=invitation.id,
            purpose=invitation.purpose,
            url=f"{get_public_url()}/invite#{token}",
            expires_at=invitation.expires_at,
        )

    def list_open(self) -> list[InvitationRead]:
        now = utcnow()
        invitations = self.db.scalars(
            select(Invitation)
            .where(Invitation.used_at.is_(None), Invitation.expires_at > now)
            .order_by(Invitation.created_at.desc(), Invitation.id.desc())
        )
        names = dict(self.db.execute(select(User.id, User.username)).all())
        return [
            InvitationRead(
                id=invitation.id,
                purpose=invitation.purpose,
                role=invitation.role,
                note=invitation.note,
                target_username=names.get(invitation.target_user_id),
                created_by_username=names.get(invitation.created_by_user_id),
                created_at=invitation.created_at,
                expires_at=invitation.expires_at,
            )
            for invitation in invitations
        ]

    def revoke(self, invitation_id: int) -> None:
        deleted = self.db.execute(
            delete(Invitation).where(Invitation.id == invitation_id, Invitation.used_at.is_(None))
        ).rowcount
        self.db.commit()
        if not deleted:
            raise AppError(status.HTTP_404_NOT_FOUND, "invitation_not_found", "Invitation not found")

    # --- Public -------------------------------------------------------------

    def inspect(self, token: str, request: Request) -> InvitationInfo:
        found = self._find_valid(token, request)
        if isinstance(found, Invite):
            return InvitationInfo(kind="group", group_name=found.group.name, expires_at=found.expires_at)
        target = self.db.get(User, found.target_user_id) if found.target_user_id else None
        return InvitationInfo(
            kind=found.purpose,
            username=target.username if target else None,
            expires_at=found.expires_at,
        )

    def accept(
        self, data: InvitationAccept, request: Request, response: Response, user: User | None
    ) -> InvitationAccepted:
        found = self._find_valid(data.token, request)
        if isinstance(found, Invite):
            return self._accept_group(found, data, request, response, user)
        if found.purpose == PURPOSE_SIGNUP:
            account = self._signup(found, data)
        else:
            account = self._reset(found, data.password or "")
        self.auth.start_session(account, request, response)
        return InvitationAccepted(kind=found.purpose, group_id=None)

    def _accept_group(
        self, invite: Invite, data: InvitationAccept, request: Request, response: Response, user: User | None
    ) -> InvitationAccepted:
        group_id = invite.group_id
        if user is not None:
            membership = self._membership(group_id, user.id)
            if membership is not None and membership.active:
                # Already in the group: the link stays usable for someone else
                return InvitationAccepted(kind="group", group_id=group_id)
            check_new_group(self.db, user.id)
        check_new_member(self.db, group_id)
        new_account = user is None
        if new_account:
            username, password = self._new_account_input(data)
        self._claim(Invite, invite.id)
        if new_account:
            user = self._create_account(username, password, data, role=None)
        membership = self._membership(group_id, user.id)
        if membership is None:
            self.db.add(Membership(group_id=group_id, user_id=user.id, role=ROLE_MEMBER))
        else:
            membership.active = True
        self.db.execute(update(Invite).where(Invite.id == invite.id).values(used_by_user_id=user.id))
        self.db.commit()
        if new_account:
            self.db.refresh(user)
            self.auth.start_session(user, request, response)
        return InvitationAccepted(kind="group", group_id=group_id)

    def _signup(self, invitation: Invitation, data: InvitationAccept) -> User:
        username, password = self._new_account_input(data)
        self._claim(Invitation, invitation.id)
        user = self._create_account(username, password, data, role=invitation.role)
        invitation.used_by_user_id = user.id
        self.db.commit()
        self.db.refresh(user)
        return user

    def _reset(self, invitation: Invitation, password: str) -> User:
        self._check_password(password)
        self._claim(Invitation, invitation.id)
        user = self.db.get(User, invitation.target_user_id)
        if user is None or not user.is_active:
            self.db.rollback()
            raise invalid()
        user.password_hash = AuthService.hash_password(password)
        invitation.used_by_user_id = user.id
        # Every device has to log in again; this browser gets a fresh session afterwards
        self.db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        self.db.commit()
        self.db.refresh(user)
        return user

    def _new_account_input(self, data: InvitationAccept) -> tuple[str, str]:
        """Check username and password before the link is used up."""
        try:
            username = normalize_username(data.username or "")
            if self.auth.repository.get_user_by_username(username) is not None:
                raise AccountError("username_taken", "Username already exists", status.HTTP_409_CONFLICT)
        except AccountError as exc:
            raise exc.to_http() from exc
        self._check_password(data.password or "")
        return username, data.password or ""

    @staticmethod
    def _check_password(password: str) -> None:
        try:
            AuthService.check_password(password)
        except AccountError as exc:
            raise exc.to_http() from exc

    def _create_account(self, username: str, password: str, data: InvitationAccept, role: str | None) -> User:
        try:
            return self.auth.create_user(
                username, password, data.display_name, role=role or "user", locale=data.locale, commit=False
            )
        except AccountError as exc:
            self.db.rollback()
            raise exc.to_http() from exc
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(status.HTTP_409_CONFLICT, "username_taken", "Username already exists") from exc

    def _claim(self, model: type[Invite] | type[Invitation], row_id: int) -> None:
        """Mark the link as used; of two simultaneous requests only one changes the row."""
        now = utcnow()
        claimed = self.db.execute(
            update(model).where(model.id == row_id, model.used_at.is_(None), model.expires_at > now).values(used_at=now)
        ).rowcount
        if claimed != 1:
            self.db.rollback()
            raise invalid()

    def _membership(self, group_id: int, user_id: int) -> Membership | None:
        return self.db.scalars(
            select(Membership).where(Membership.group_id == group_id, Membership.user_id == user_id)
        ).first()

    def _find_valid(self, token: str, request: Request) -> Invite | Invitation:
        ip_address = client_ip(request)
        invitation_rate_limiter.check(ip_address, ip_address)
        token_hash = AuthService.hash_token(token.strip())
        now = utcnow()
        found: Invite | Invitation | None = self.db.scalars(
            select(Invitation).where(Invitation.token_hash == token_hash)
        ).first()
        if found is None:
            found = self.db.scalars(select(Invite).where(Invite.token_hash == token_hash)).first()
        if found is None or found.used_at is not None or found.expires_at <= now:
            invitation_rate_limiter.record_failure(ip_address, ip_address)
            raise invalid()
        return found

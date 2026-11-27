"""One-time links: into a group, to create an account, to set a new password, to confirm an
e-mail address, or to finish an open registration.

Every link is PUBLIC_URL/invite#<token>. The token sits in the URL fragment, so it never
reaches server logs or Referer headers; the web app reads it and sends it in the body.
Only its SHA-256 hash is stored. Using a link is atomic: the first request that marks it
as used wins, a second one finds it invalid.

With e-mail set up, links can also be sent by mail. Requests that start from an address
(forgotten password, registration) always get the same answer, so they do not reveal
whether an address or account exists.
"""

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, Request, Response, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_invite_expiry_days, get_public_url
from app.errors import AppError
from app.models.audit import AuditEntry
from app.models.group import Group, Invite, Membership
from app.models.invitation import (
    PURPOSE_PASSWORD_RESET,
    PURPOSE_REGISTRATION,
    PURPOSE_SIGNUP,
    PURPOSE_VERIFY_EMAIL,
    Invitation,
)
from app.models.user import AUTH_OIDC, AUTH_PASSWORD, NO_PASSWORD, User, UserSession
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import RegisterRequest
from app.schemas.invitation import (
    InvitationAccept,
    InvitationAccepted,
    InvitationCreated,
    InvitationInfo,
    InvitationRead,
)
from app.services import mail_texts
from app.services.auth_service import AccountError, AuthService, normalize_username, require_password_login, utcnow
from app.services.limits import check_new_group, check_new_member
from app.services.login_rate_limiter import LoginRateLimiter
from app.services.mail import Mail, check_account_quota, require_mail, send_later
from app.services.placeholders import reassign

RESET_EXPIRY = timedelta(hours=24)
# Requested by the person: shorter, the mail is read right away
SELF_RESET_EXPIRY = timedelta(hours=1)
VERIFY_EXPIRY = timedelta(days=2)
# Used and expired links are kept a while for reference, then removed
KEEP_FINISHED = timedelta(days=30)
# Links an instance admin manages (the others belong to the person)
ADMIN_PURPOSES = (PURPOSE_SIGNUP, PURPOSE_PASSWORD_RESET)
# Wrong tokens per IP address: 20 in 15 minutes (the limiter is keyed by the IP twice)
invitation_rate_limiter = LoginRateLimiter()
invitation_rate_limiter.account_limit = invitation_rate_limiter.ip_limit
# "Forgot password": 10 requests per IP address and 3 mails per account per hour
reset_ip_limiter = LoginRateLimiter(window_seconds=60 * 60)
reset_ip_limiter.account_limit = reset_ip_limiter.ip_limit = 10
reset_account_limiter = LoginRateLimiter(window_seconds=60 * 60)
reset_account_limiter.account_limit = 3
reset_account_limiter.ip_limit = 10**9


def invalid() -> AppError:
    return AppError(status.HTTP_404_NOT_FOUND, "invite_invalid", "This link is invalid, expired or already used")


def email_taken() -> AppError:
    return AppError(status.HTTP_409_CONFLICT, "email_taken", "This address belongs to another account")


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def new_token() -> tuple[str, str]:
    """A token and its stored hash."""
    token = secrets.token_urlsafe(32)
    return token, AuthService.hash_token(token)


def link(token: str) -> str:
    return f"{get_public_url()}/invite#{token}"


@dataclass(frozen=True)
class External:
    """A link used through the OIDC provider: the account gets no password, `attach` links it.

    `attach` runs before the change is committed, so a failed link leaves the invitation unused.
    """

    attach: Callable[[User], None]


# Links that can be used through the provider (not: confirming an address, finishing a registration)
EXTERNAL_KINDS = ("group", "personal", PURPOSE_SIGNUP, PURPOSE_PASSWORD_RESET)


class InvitationService:
    def __init__(self, db: Session, background: BackgroundTasks | None = None):
        self.db = db
        self.background = background
        self.auth = AuthService(AuthRepository(db))

    def _send(self, mail: Mail) -> None:
        if self.background is None:
            raise RuntimeError("Sending needs BackgroundTasks")
        send_later(self.background, mail)

    # --- Instance admin -----------------------------------------------------

    def create_signup(
        self, admin: User, role: str, note: str | None, email: str | None = None, request: Request | None = None
    ) -> InvitationCreated:
        if email:
            require_mail()
            check_account_quota(admin.id, client_ip(request) if request else "unknown")
        now = utcnow()
        invitation = Invitation(
            purpose=PURPOSE_SIGNUP,
            role=role,
            note=note,
            email=email,
            created_by_user_id=admin.id,
            expires_at=now + timedelta(days=get_invite_expiry_days()),
        )
        token = self._create(invitation, now)
        if email:
            locale = mail_texts.pick_locale(admin.locale, request=request)
            self._send(mail_texts.signup_invite(email, locale, admin.display_name, link(token), invitation.expires_at))
        return self._created(invitation, token, email_sent=bool(email))

    def create_password_reset(
        self, admin: User | None, target: User, send_email: bool = False, request: Request | None = None
    ) -> InvitationCreated:
        """A link to set a new password: by an admin (shown, optionally mailed) or requested by mail."""
        if not target.is_active:
            raise AppError(status.HTTP_409_CONFLICT, "account_inactive", "Reactivate the account first")
        if send_email:
            require_mail()
            if not target.email:
                raise AppError(status.HTTP_409_CONFLICT, "no_email", "This account has no confirmed e-mail address")
        now = utcnow()
        # Only the newest reset link for an account works
        self.db.execute(
            delete(Invitation).where(
                Invitation.purpose == PURPOSE_PASSWORD_RESET,
                Invitation.target_user_id == target.id,
                Invitation.used_at.is_(None),
            )
        )
        invitation = Invitation(
            purpose=PURPOSE_PASSWORD_RESET,
            target_user_id=target.id,
            created_by_user_id=admin.id if admin else None,
            email=target.email if send_email else None,
            expires_at=now + (RESET_EXPIRY if admin else SELF_RESET_EXPIRY),
        )
        token = self._create(invitation, now)
        if send_email and target.email:
            locale = mail_texts.pick_locale(target.locale, request=request)
            self._send(
                mail_texts.password_reset(target.email, locale, target.username, link(token), invitation.expires_at)
            )
        return self._created(invitation, token, email_sent=send_email)

    def _create(self, invitation: Invitation, now: datetime) -> str:
        self.db.execute(
            delete(Invitation).where(
                or_(Invitation.used_at.is_not(None), Invitation.expires_at <= now),
                Invitation.expires_at <= now - KEEP_FINISHED,
            )
        )
        token, invitation.token_hash = new_token()
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        return token

    @staticmethod
    def _created(invitation: Invitation, token: str, email_sent: bool = False) -> InvitationCreated:
        return InvitationCreated(
            id=invitation.id,
            purpose=invitation.purpose,
            url=link(token),
            expires_at=invitation.expires_at,
            email_sent=email_sent,
        )

    def list_open(self) -> list[InvitationRead]:
        now = utcnow()
        invitations = self.db.scalars(
            select(Invitation)
            .where(
                Invitation.used_at.is_(None),
                Invitation.expires_at > now,
                Invitation.purpose.in_(ADMIN_PURPOSES),
                Invitation.created_by_user_id.is_not(None),
            )
            .order_by(Invitation.created_at.desc(), Invitation.id.desc())
        )
        names = dict(self.db.execute(select(User.id, User.username)).all())
        return [
            InvitationRead(
                id=invitation.id,
                purpose=invitation.purpose,
                role=invitation.role,
                note=invitation.note,
                email=invitation.email,
                target_username=names.get(invitation.target_user_id),
                created_by_username=names.get(invitation.created_by_user_id),
                created_at=invitation.created_at,
                expires_at=invitation.expires_at,
            )
            for invitation in invitations
        ]

    def revoke(self, invitation_id: int) -> None:
        deleted = self.db.execute(
            delete(Invitation).where(
                Invitation.id == invitation_id,
                Invitation.used_at.is_(None),
                Invitation.purpose.in_(ADMIN_PURPOSES),
            )
        ).rowcount
        self.db.commit()
        if not deleted:
            raise AppError(status.HTTP_404_NOT_FOUND, "invitation_not_found", "Invitation not found")

    # --- Group admins -------------------------------------------------------

    def send_group_invite(
        self,
        inviter: User,
        group: Group,
        created: dict,
        email: str,
        request: Request,
        member_name: str | None = None,
    ) -> None:
        """Mail a group link that was just created (require_mail and the quota were checked before)."""
        locale = mail_texts.pick_locale(inviter.locale, request=request)
        self._send(
            mail_texts.group_invite(
                email, locale, inviter.display_name, group.name, created["url"], created["expires_at"], member_name
            )
        )

    # --- The person themselves ---------------------------------------------

    def request_password_reset(self, login: str, request: Request) -> None:
        """'Forgot password': mails a link if the account has a confirmed address; silent otherwise."""
        require_mail()
        ip_address = client_ip(request)
        reset_ip_limiter.check(ip_address, ip_address)
        reset_ip_limiter.record_failure(ip_address, ip_address)
        value = login.strip().lower()
        user = self.db.scalars(select(User).where(or_(User.username == value, User.email == value))).first()
        if user is None or not user.is_active or user.placeholder or not user.email:
            return
        key = f"user-{user.id}"
        try:
            reset_account_limiter.check(key, "-")
        except AppError:
            # Enough mails for this account for now; the answer stays the same
            return
        reset_account_limiter.record_failure(key, "-")
        self.create_password_reset(None, user, send_email=True, request=request)

    def request_email_change(self, user: User, email: str, request: Request) -> None:
        """Send a confirmation link to the new address; the address counts once confirmed."""
        require_mail()
        check_account_quota(user.id, client_ip(request))
        if email == user.email:
            return
        now = utcnow()
        self.db.execute(
            delete(Invitation).where(
                Invitation.purpose == PURPOSE_VERIFY_EMAIL,
                Invitation.target_user_id == user.id,
                Invitation.used_at.is_(None),
            )
        )
        invitation = Invitation(
            purpose=PURPOSE_VERIFY_EMAIL,
            target_user_id=user.id,
            email=email,
            created_by_user_id=user.id,
            expires_at=now + VERIFY_EXPIRY,
        )
        token = self._create(invitation, now)
        locale = mail_texts.pick_locale(user.locale, request=request)
        self._send(mail_texts.verify_email(email, locale, user.username, link(token), invitation.expires_at))

    def pending_email(self, user: User) -> str | None:
        return self.db.scalar(
            select(Invitation.email)
            .where(
                Invitation.purpose == PURPOSE_VERIFY_EMAIL,
                Invitation.target_user_id == user.id,
                Invitation.used_at.is_(None),
                Invitation.expires_at > utcnow(),
            )
            .order_by(Invitation.id.desc())
            .limit(1)
        )

    def cancel_email_change(self, user: User) -> None:
        self.db.execute(
            delete(Invitation).where(
                Invitation.purpose == PURPOSE_VERIFY_EMAIL,
                Invitation.target_user_id == user.id,
                Invitation.used_at.is_(None),
            )
        )
        self.db.commit()

    def start_registration(self, data: RegisterRequest, request: Request) -> None:
        """Open registration with e-mail: the account is created when the link in the mail is used."""
        locale = mail_texts.pick_locale(data.locale, request=request)
        username, password = self._new_account_input(data.username, data.password)
        email = data.email or ""
        existing = self.db.scalars(select(User).where(User.email == email)).first()
        if existing is not None:
            # Same answer as for a new address; the owner learns about it by mail
            if existing.is_active:
                self._send(
                    mail_texts.registration_existing(
                        email, mail_texts.pick_locale(existing.locale, locale), existing.username
                    )
                )
            return
        now = utcnow()
        # Only the newest registration of an address works
        self.db.execute(
            delete(Invitation).where(
                Invitation.purpose == PURPOSE_REGISTRATION,
                Invitation.email == email,
                Invitation.used_at.is_(None),
            )
        )
        invitation = Invitation(
            purpose=PURPOSE_REGISTRATION,
            email=email,
            username=username,
            display_name=(data.display_name or "").strip() or None,
            password_hash=AuthService.hash_password(password),
            locale=data.locale,
            expires_at=now + VERIFY_EXPIRY,
        )
        token = self._create(invitation, now)
        self._send(mail_texts.registration(email, locale, username, link(token), invitation.expires_at))

    # --- Public -------------------------------------------------------------

    def inspect(self, token: str, request: Request) -> InvitationInfo:
        found = self._find_valid(token, request)
        if isinstance(found, Invite):
            placeholder = self.db.get(User, found.placeholder_user_id) if found.placeholder_user_id else None
            return InvitationInfo(
                kind="group",
                group_name=found.group.name,
                member_name=placeholder.display_name if placeholder else None,
                expires_at=found.expires_at,
            )
        target = self.db.get(User, found.target_user_id) if found.target_user_id else None
        return InvitationInfo(
            kind=found.purpose,
            username=target.username if target else found.username,
            email=found.email if found.purpose in (PURPOSE_VERIFY_EMAIL, PURPOSE_REGISTRATION) else None,
            expires_at=found.expires_at,
        )

    def accept(
        self, data: InvitationAccept, request: Request, response: Response, user: User | None
    ) -> InvitationAccepted:
        found = self._find_valid(data.token, request)
        return self._accept_found(found, data, request, response, user, None)

    # --- Through the OIDC provider --------------------------------------------

    def find_for_provider(self, token: str, request: Request) -> Invite | Invitation:
        """The link behind a token, if it can be used through the provider (checked before the redirect)."""
        found = self._find_valid(token, request)
        if kind_of(found) not in EXTERNAL_KINDS:
            raise AppError(status.HTTP_409_CONFLICT, "oidc_not_for_link", "This link cannot be used with the provider")
        return found

    def check_new_username(self, username: str | None) -> str:
        """Check the chosen username before the redirect, so a mistake shows on the form."""
        try:
            name = normalize_username(username or "")
        except AccountError as exc:
            raise exc.to_http() from exc
        if self.auth.repository.get_user_by_username(name) is not None:
            raise AppError(status.HTTP_409_CONFLICT, "username_taken", "Username already exists")
        return name

    def accept_external(
        self,
        model: type[Invite] | type[Invitation],
        row_id: int,
        data: InvitationAccept,
        request: Request,
        response: Response,
        external: External,
    ) -> InvitationAccepted:
        """Finish a link after the provider: the link was found by its token before the redirect."""
        found = self.db.get(model, row_id)
        if found is None or found.used_at is not None or found.expires_at <= utcnow():
            raise invalid()
        if kind_of(found) not in EXTERNAL_KINDS:
            raise invalid()
        return self._accept_found(found, data, request, response, None, external)

    def _accept_found(
        self,
        found: Invite | Invitation,
        data: InvitationAccept,
        request: Request,
        response: Response,
        user: User | None,
        external: External | None,
    ) -> InvitationAccepted:
        if isinstance(found, Invite):
            if found.placeholder_user_id is not None:
                return self._accept_personal(found, data, request, response, user, external)
            return self._accept_group(found, data, request, response, user, external)
        if found.purpose == PURPOSE_VERIFY_EMAIL:
            self._verify_email(found, request)
            return InvitationAccepted(kind=found.purpose, group_id=None)
        if found.purpose == PURPOSE_SIGNUP:
            account = self._signup(found, data, external)
        elif found.purpose == PURPOSE_REGISTRATION:
            account = self._finish_registration(found)
        elif external is not None:
            account = self._recover(found, external)
        else:
            account = self._reset(found, data.password or "")
        self.auth.start_session(account, request, response, AUTH_OIDC if external else AUTH_PASSWORD)
        return InvitationAccepted(kind=found.purpose, group_id=None)

    def _accept_group(
        self,
        invite: Invite,
        data: InvitationAccept,
        request: Request,
        response: Response,
        user: User | None,
        external: External | None = None,
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
            username, password = self._new_account_input(data.username, data.password, external)
        self._claim(Invite, invite.id)
        if new_account:
            user = self._create_account(username, password, data, role=None, email=invite.email)
            if external is not None:
                external.attach(user)
        membership = self._membership(group_id, user.id)
        if membership is None:
            self.db.add(Membership(group_id=group_id, user_id=user.id))
        else:
            membership.active = True
        self.db.execute(update(Invite).where(Invite.id == invite.id).values(used_by_user_id=user.id))
        self.db.commit()
        if new_account:
            self.db.refresh(user)
            self.auth.start_session(user, request, response, AUTH_OIDC if external else AUTH_PASSWORD)
        return InvitationAccepted(kind="group", group_id=group_id)

    def _accept_personal(
        self,
        invite: Invite,
        data: InvitationAccept,
        request: Request,
        response: Response,
        user: User | None,
        external: External | None = None,
    ) -> InvitationAccepted:
        """A personal link: the new or logged-in account takes over a placeholder member."""
        group_id = invite.group_id
        placeholder = self.db.get(User, invite.placeholder_user_id)
        place = self._membership(group_id, placeholder.id) if placeholder else None
        if placeholder is None or not placeholder.placeholder or place is None or not place.active:
            raise invalid()
        if user is not None:
            if self._membership(group_id, user.id) is not None:
                raise AppError(
                    status.HTTP_409_CONFLICT,
                    "already_in_group",
                    "You are already in this group; this link is meant for someone else",
                )
            check_new_group(self.db, user.id)
            self._claim(Invite, invite.id)
            reassign(self.db, group_id, placeholder.id, user.id)
            self.db.execute(
                update(Invite).where(Invite.id == invite.id).values(used_by_user_id=user.id, placeholder_user_id=None)
            )
            self.db.execute(delete(User).where(User.id == placeholder.id))
            account, new_account = user, False
        else:
            username, password = self._new_account_input(data.username, data.password, external)
            self._claim(Invite, invite.id)
            # The placeholder row becomes the account: its bookings are already its own
            placeholder.username = username
            placeholder.password_hash = AuthService.hash_password(password) if password is not None else NO_PASSWORD
            placeholder.display_name = (data.display_name or "").strip() or placeholder.display_name
            placeholder.locale = data.locale
            placeholder.placeholder = False
            placeholder.is_active = True
            placeholder.email = self._free_email(invite.email)
            self.db.execute(update(Invite).where(Invite.id == invite.id).values(used_by_user_id=placeholder.id))
            if external is not None:
                self.db.flush()
                external.attach(placeholder)
            account, new_account = placeholder, True
        self.db.add(
            AuditEntry(
                group_id=group_id,
                user_id=account.id,
                entity="member",
                entity_id=account.id,
                action="claim",
                diff_json=json.dumps({"new_account": new_account}),
            )
        )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(status.HTTP_409_CONFLICT, "username_taken", "Username already exists") from exc
        if new_account:
            self.db.refresh(account)
            self.auth.start_session(account, request, response, AUTH_OIDC if external else AUTH_PASSWORD)
        return InvitationAccepted(kind="group", group_id=group_id)

    def _signup(self, invitation: Invitation, data: InvitationAccept, external: External | None = None) -> User:
        username, password = self._new_account_input(data.username, data.password, external)
        self._claim(Invitation, invitation.id)
        user = self._create_account(username, password, data, role=invitation.role, email=invitation.email)
        if external is not None:
            external.attach(user)
        invitation.used_by_user_id = user.id
        self.db.commit()
        self.db.refresh(user)
        return user

    def _finish_registration(self, invitation: Invitation) -> User:
        if self.auth.repository.get_user_by_username(invitation.username or "") is not None:
            raise AppError(
                status.HTTP_409_CONFLICT, "username_taken", "Someone took this username in the meantime; register again"
            )
        if self._free_email(invitation.email) is None:
            raise email_taken()
        self._claim(Invitation, invitation.id)
        user = User(
            username=invitation.username,
            display_name=invitation.display_name or invitation.username,
            password_hash=invitation.password_hash,
            locale=invitation.locale,
            email=invitation.email,
        )
        self.db.add(user)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(status.HTTP_409_CONFLICT, "username_taken", "Username already exists") from exc
        invitation.used_by_user_id = user.id
        invitation.password_hash = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def _verify_email(self, invitation: Invitation, request: Request) -> None:
        user = self.db.get(User, invitation.target_user_id)
        if user is None or not user.is_active:
            raise invalid()
        if self._free_email(invitation.email, except_user_id=user.id) is None:
            raise email_taken()
        self._claim(Invitation, invitation.id)
        previous = user.email
        user.email = invitation.email
        invitation.used_by_user_id = user.id
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise email_taken() from exc
        if previous and previous != user.email:
            locale = mail_texts.pick_locale(user.locale, request=request)
            self._send(mail_texts.email_changed(previous, locale, user.username))

    def _reset(self, invitation: Invitation, password: str) -> User:
        require_password_login()
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

    def _recover(self, invitation: Invitation, external: External) -> User:
        """A password-reset link used through the provider: link the account instead of a new password."""
        self._claim(Invitation, invitation.id)
        user = self.db.get(User, invitation.target_user_id)
        if user is None or not user.is_active:
            self.db.rollback()
            raise invalid()
        external.attach(user)
        invitation.used_by_user_id = user.id
        # Every device has to log in again; this browser gets a fresh session afterwards
        self.db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        self.db.commit()
        self.db.refresh(user)
        return user

    def _free_email(self, email: str | None, except_user_id: int | None = None) -> str | None:
        """The address if no other account uses it, else None."""
        if not email:
            return None
        query = select(func.count()).select_from(User).where(User.email == email)
        if except_user_id is not None:
            query = query.where(User.id != except_user_id)
        return None if self.db.scalar(query) else email

    def _new_account_input(
        self, username_in: str | None, password: str | None, external: External | None = None
    ) -> tuple[str, str | None]:
        """Check username and password before the link is used up; through the provider, no password."""
        try:
            username = normalize_username(username_in or "")
            if self.auth.repository.get_user_by_username(username) is not None:
                raise AccountError("username_taken", "Username already exists", status.HTTP_409_CONFLICT)
        except AccountError as exc:
            raise exc.to_http() from exc
        if external is not None:
            return username, None
        require_password_login()
        self._check_password(password or "")
        return username, password or ""

    @staticmethod
    def _check_password(password: str) -> None:
        try:
            AuthService.check_password(password)
        except AccountError as exc:
            raise exc.to_http() from exc

    def _create_account(
        self, username: str, password: str | None, data: InvitationAccept, role: str | None, email: str | None = None
    ) -> User:
        try:
            user = self.auth.create_user(
                username, password, data.display_name, role=role or "user", locale=data.locale, commit=False
            )
        except AccountError as exc:
            self.db.rollback()
            raise exc.to_http() from exc
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError(status.HTTP_409_CONFLICT, "username_taken", "Username already exists") from exc
        # The link came by mail to this address, which confirms it
        user.email = self._free_email(email)
        return user

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


def kind_of(found: Invite | Invitation) -> str:
    if isinstance(found, Invite):
        return "personal" if found.placeholder_user_id is not None else "group"
    return found.purpose

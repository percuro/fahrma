"""Self-service for the logged-in account: password, devices, data export, deletion."""

import json
from datetime import timedelta

from fastapi import Request, Response, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_oidc_settings
from app.errors import AppError
from app.models.audit import AuditEntry
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import ROLE_ADMIN, ROLE_MEMBER, Group, Invite, Membership
from app.models.idempotency import IdempotencyKey
from app.models.invitation import Invitation
from app.models.oidc_state import OidcLoginState
from app.models.push import PushSubscription, SentNotification
from app.models.reservation import Reservation
from app.models.settlement import Settlement, SettlementTransfer
from app.models.trip import Trip, TripExternalPayment, TripShare
from app.models.user import AUTH_OIDC, NO_PASSWORD, ROLE_USER, OidcIdentity, User
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import DeletionPreview, SessionRead
from app.services.auth_service import AccountError, AuthService, clear_session_cookie, require_password_login, utcnow
from app.services.client_address import client_ip
from app.services.devices import describe_user_agent
from app.services.group_service import delete_group_data
from app.services.login_rate_limiter import login_rate_limiter
from app.services.notification_service import export_rows as notification_export
from app.services.reservation_service import delete_upcoming
from app.services.rows import row_dict

EXPORT_FORMAT = "fahrma-account/1"
# Without a password, a sensitive change needs a login at the provider this recent
REAUTH_WINDOW = timedelta(minutes=10)


def anonymous_name(user_id: int) -> str:
    """Name of a deleted account; "Person" reads the same in German and English."""
    return f"Person {user_id}"


class AccountService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AuthRepository(db)

    # --- Password and devices -----------------------------------------------

    def confirm(self, user: User, password: str | None, request: Request, session_id: int) -> None:
        """Make sure it is really the account holder before a sensitive change.

        With a password: re-check it. Without one (OIDC only): the session must have logged in
        at the provider within the last few minutes, otherwise 403 reauth_required and the
        web app sends the person through the provider again.
        """
        if user.has_password:
            self.verify_password(user, password or "", request)
            return
        self.require_fresh_provider_login(user, session_id)

    def require_fresh_provider_login(self, user: User, session_id: int) -> None:
        """403 reauth_required unless this session logged in at the provider in the last few minutes."""
        session = self.repository.get_session_for_user(session_id, user.id)
        authenticated_at = (session.authenticated_at or session.created_at) if session is not None else None
        if (
            session is None
            or session.auth_method != AUTH_OIDC
            or authenticated_at is None
            or authenticated_at < utcnow() - REAUTH_WINDOW
        ):
            raise AppError(status.HTTP_403_FORBIDDEN, "reauth_required", "Log in at the provider again to confirm")

    def verify_password(self, user: User, password: str, request: Request) -> None:
        """Re-check the password before a sensitive change; limited like the login."""
        ip_address = client_ip(request)
        login_rate_limiter.check(user.username, ip_address)
        if not AuthService.verify_password(password, user.password_hash):
            login_rate_limiter.record_failure(user.username, ip_address)
            # 403, not 401: the session is fine, only the confirmation failed
            raise AppError(status.HTTP_403_FORBIDDEN, "wrong_password", "The password is wrong")
        login_rate_limiter.record_success(user.username)

    def change_password(self, user: User, current: str | None, new: str, request: Request, session_id: int) -> None:
        """Change the password, or set a first one for an account that logs in through OIDC."""
        require_password_login()
        self.confirm(user, current, request, session_id)
        try:
            AuthService.check_password(new)
        except AccountError as exc:
            raise exc.to_http() from exc
        user.password_hash = AuthService.hash_password(new)
        self.db.commit()
        # Every other device has to log in again with the new password
        self.repository.delete_sessions(user.id, keep_session_id=session_id)

    def remove_password(self, user: User, session_id: int) -> None:
        """Log in with the provider only: the password stops working, other devices are logged out.

        Needs a fresh login at the provider, which also shows that the link works right now, so
        nobody locks themselves out. "Forgot password" by mail no longer applies to the account;
        an instance admin can still create a password-reset link.
        """
        if not user.has_password:
            raise AppError(status.HTTP_409_CONFLICT, "no_password", "This account has no password")
        if get_oidc_settings() is None or user.oidc_identity is None:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "oidc_not_linked",
                "Link the account with the provider first; without a password it could not log in otherwise",
            )
        self.require_fresh_provider_login(user, session_id)
        user.password_hash = NO_PASSWORD
        self.db.commit()
        self.repository.delete_sessions(user.id, keep_session_id=session_id)

    def sessions(self, user: User, current_session_id: int) -> list[SessionRead]:
        return [
            SessionRead(
                id=session.id,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                device=describe_user_agent(session.user_agent),
                current=session.id == current_session_id,
                auth_method=session.auth_method,
            )
            for session in self.repository.list_sessions(user.id, utcnow())
        ]

    def revoke_session(self, user: User, session_id: int) -> None:
        session = self.repository.get_session_for_user(session_id, user.id)
        if session is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "session_not_found", "Session not found")
        self.repository.delete_session(session)

    def revoke_other_sessions(self, user: User, current_session_id: int) -> int:
        return self.repository.delete_sessions(user.id, keep_session_id=current_session_id)

    # --- Deletion -----------------------------------------------------------

    def ensure_not_last_admin(self, user: User) -> None:
        if user.is_admin and user.is_active and self.repository.count_active_admins(exclude_user_id=user.id) == 0:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "last_instance_admin",
                "The last active admin of this instance cannot be removed or demoted",
            )

    def deletion_preview(self, user: User) -> DeletionPreview:
        deleted, handover, kept = self._deletion_plan(user)
        return DeletionPreview(
            groups_deleted=[{"id": group.id, "name": group.name} for group in deleted],
            admin_handover=[
                {"group_id": group.id, "group_name": group.name, "new_admin_name": successor.user.display_name}
                for group, successor in handover
            ],
            groups_kept=[{"id": group.id, "name": group.name} for group in kept],
        )

    def delete_own(
        self, user: User, password: str | None, request: Request, response: Response, session_id: int
    ) -> None:
        self.confirm(user, password, request, session_id)
        self.delete(user)
        clear_session_cookie(response)

    def delete(self, user: User) -> None:
        """Delete an account; the bookings of its groups stay under an anonymous name.

        - Groups without another active member are deleted completely.
        - Where the account is the last admin, the longest-standing active member takes over.
        - Login, sessions, username, display name and language are removed; the name also
          disappears from the frozen settlement snapshots.
        """
        self.ensure_not_last_admin(user)
        deleted, handover, _kept = self._deletion_plan(user)
        for group in deleted:
            delete_group_data(self.db, group.id)
        for group, successor in handover:
            successor.role = ROLE_ADMIN
            self.db.add(
                AuditEntry(
                    group_id=group.id,
                    user_id=user.id,
                    entity="member",
                    entity_id=successor.user_id,
                    action="update",
                    diff_json=json.dumps({"role": ROLE_ADMIN, "reason": "account_deleted"}),
                )
            )
        self.db.execute(update(Membership).where(Membership.user_id == user.id).values(active=False, role=ROLE_MEMBER))
        self._anonymize_snapshots(user)
        # Open links of this account stop working
        self.db.execute(delete(Invite).where(Invite.created_by == user.id, Invite.used_at.is_(None)))
        self.db.execute(
            delete(Invitation).where(
                or_(Invitation.target_user_id == user.id, Invitation.created_by_user_id == user.id),
                Invitation.used_at.is_(None),
            )
        )
        self.db.execute(delete(IdempotencyKey).where(IdempotencyKey.user_id == user.id))
        delete_upcoming(self.db, user.id, utcnow())
        self.db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id))
        self.db.execute(delete(SentNotification).where(SentNotification.user_id == user.id))
        self.repository.delete_sessions(user.id, commit=False)
        # The provider's subject could otherwise still log in to the empty account
        self.db.execute(delete(OidcIdentity).where(OidcIdentity.user_id == user.id))
        self.db.execute(delete(OidcLoginState).where(OidcLoginState.user_id == user.id))
        user.username = f"~deleted-{user.id}"  # "~" is not allowed in usernames, so it never collides
        user.display_name = anonymous_name(user.id)
        user.password_hash = NO_PASSWORD
        user.email = None
        user.locale = None
        user.notify = None
        user.inactivity_warned_at = None
        user.role = ROLE_USER
        user.is_active = False
        user.last_seen_at = None
        user.deleted_at = utcnow()
        self.db.commit()

    def _deletion_plan(self, user: User) -> tuple[list[Group], list[tuple[Group, Membership]], list[Group]]:
        deleted: list[Group] = []
        handover: list[tuple[Group, Membership]] = []
        kept: list[Group] = []
        own = self.db.scalars(
            select(Membership).where(Membership.user_id == user.id, Membership.active.is_(True))
        ).all()
        for membership in own:
            # Placeholders cannot look after a group, so they do not keep it alive
            others = self.db.scalars(
                select(Membership)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.group_id == membership.group_id,
                    Membership.user_id != user.id,
                    Membership.active.is_(True),
                    User.placeholder.is_(False),
                )
                .order_by(Membership.created_at, Membership.id)
            ).all()
            group = membership.group
            if not others:
                deleted.append(group)
                continue
            kept.append(group)
            if membership.role == ROLE_ADMIN and not any(other.role == ROLE_ADMIN for other in others):
                handover.append((group, others[0]))
        return deleted, handover, kept

    def _anonymize_snapshots(self, user: User) -> None:
        group_ids = select(Membership.group_id).where(Membership.user_id == user.id)
        name = anonymous_name(user.id)
        for settlement in self.db.scalars(select(Settlement).where(Settlement.group_id.in_(group_ids))):
            snapshot = json.loads(settlement.snapshot_json)
            changed = False
            for member in snapshot.get("members", []):
                if member.get("user_id") == user.id:
                    member["display_name"] = name
                    changed = True
            if changed:
                settlement.snapshot_json = json.dumps(snapshot, ensure_ascii=False)

    # --- Data export --------------------------------------------------------

    def export(self, user: User) -> dict:
        """Everything stored about the account and every entry it is part of ("my data")."""
        uid = user.id
        memberships = self.db.scalars(select(Membership).where(Membership.user_id == uid)).all()
        trip_ids = select(TripShare.trip_id).where(TripShare.user_id == uid)
        trips = self.db.scalars(select(Trip).where(or_(Trip.created_by == uid, Trip.id.in_(trip_ids)))).all()
        selected_trip_ids = [trip.id for trip in trips]

        def rows(query) -> list[dict]:
            return [row_dict(row) for row in self.db.scalars(query)]

        return {
            "format": EXPORT_FORMAT,
            "exported_at": utcnow().isoformat(),
            "account": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "locale": user.locale,
                "role": user.role,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
                "has_password": user.has_password,
            },
            "oidc": _oidc_export(user.oidc_identity),
            "sessions": [
                {
                    "created_at": session.created_at.isoformat(),
                    "last_seen_at": session.last_seen_at.isoformat() if session.last_seen_at else None,
                    "device": describe_user_agent(session.user_agent),
                    "auth_method": session.auth_method,
                }
                for session in self.repository.list_sessions(uid, utcnow())
            ],
            "groups": [
                {
                    "id": membership.group_id,
                    "name": membership.group.name,
                    "role": membership.role,
                    "active": membership.active,
                    "joined_at": membership.created_at.isoformat(),
                }
                for membership in memberships
            ],
            "trips": [row_dict(trip) for trip in trips],
            "trip_shares": rows(select(TripShare).where(TripShare.trip_id.in_(selected_trip_ids))),
            "trip_external_payments": rows(
                select(TripExternalPayment).where(
                    or_(
                        TripExternalPayment.received_by_user_id == uid,
                        TripExternalPayment.trip_id.in_(selected_trip_ids),
                    )
                )
            ),
            "fuel": rows(select(FuelEntry).where(or_(FuelEntry.paid_by_user_id == uid, FuelEntry.created_by == uid))),
            "expenses": rows(
                select(Expense).where(
                    or_(Expense.paid_by_user_id == uid, Expense.allocated_user_id == uid, Expense.created_by == uid)
                )
            ),
            "transfers": rows(
                select(SettlementTransfer).where(
                    or_(SettlementTransfer.from_user_id == uid, SettlementTransfer.to_user_id == uid)
                )
            ),
            "notifications": notification_export(self.db, user),
            "reservations": rows(
                select(Reservation)
                .where(or_(Reservation.user_id == uid, Reservation.created_by == uid))
                .order_by(Reservation.starts_at)
            ),
        }


def _oidc_export(link: OidcIdentity | None) -> dict | None:
    if link is None:
        return None
    return {
        "issuer": link.issuer,
        "subject": link.subject,
        "email": link.email,
        "preferred_username": link.preferred_username,
        "linked_at": link.created_at.isoformat(),
        "last_login_at": link.last_login_at.isoformat() if link.last_login_at else None,
    }

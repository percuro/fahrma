"""Login through the OIDC provider: starting it, and finishing it in the callback.

Every start writes a short-lived OidcLoginState (what to do afterwards, PKCE verifier, nonce) and
gives the browser the raw state in a cookie. The callback only continues when the state in the URL
matches that cookie, so nobody can make a victim's browser finish a login they did not start.
Accounts are matched by issuer + subject only, never by e-mail address.

The callback always answers with a redirect into the web app. Errors travel in the URL fragment
(/login#error=oidc_no_account), so they do not end up in proxy logs.
"""

import hmac
import json
import logging
import re
import secrets
from datetime import UTC, timedelta

from fastapi import Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import (
    OidcSettings,
    get_oidc_redirect_uri,
    get_oidc_settings,
    get_public_url,
    get_registration_mode,
)
from app.errors import AppError
from app.models.group import Invite
from app.models.invitation import Invitation
from app.models.oidc_state import (
    PURPOSE_INVITE,
    PURPOSE_LINK,
    PURPOSE_LOGIN,
    PURPOSE_REAUTH,
    PURPOSE_REGISTER,
    PURPOSE_SETUP,
    OidcLoginState,
)
from app.models.user import AUTH_OIDC, NO_PASSWORD, ROLE_ADMIN, ROLE_USER, OidcIdentity, User, UserSession
from app.repositories.auth_repository import AuthRepository
from app.schemas.invitation import InvitationAccept
from app.services import setup_service
from app.services.auth_service import USERNAME_PATTERN, AuthService, cookie_settings, utcnow
from app.services.client_address import client_ip
from app.services.invitation_service import External, InvitationService
from app.services.login_rate_limiter import LoginRateLimiter
from app.services.oidc_client import Identity, OidcClient, OidcError, get_client, pkce_pair

logger = logging.getLogger(__name__)

STATE_COOKIE_NAME = "fahrma_oidc"
STATE_TTL = timedelta(minutes=10)
# Where the web app may be sent back to after link/reauth
RETURN_PATHS = ("/", "/profile", "/admin")
# Starts and failed callbacks per IP address (each start writes a row)
oidc_rate_limiter = LoginRateLimiter("oidc", account_limit=30, ip_limit=30)


def require_settings() -> OidcSettings:
    settings = get_oidc_settings()
    if settings is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "oidc_disabled", "Login through OIDC is not configured")
    return settings


def client_for(settings: OidcSettings) -> OidcClient:
    """Separate function so tests can plug in a fake provider."""
    return get_client(settings)


def hash_state(state: str) -> str:
    return AuthService.hash_token(state)


def _cookie_path(request: Request) -> str:
    # The API is mounted under /api; the callback lives at <root>/v1/auth/oidc/callback
    return f"{request.scope.get('root_path', '')}/v1/auth/oidc"


def suggest_username(identity: Identity) -> str:
    """A valid username from what the provider tells us (preferred_username, e-mail, else "user")."""
    candidates = [identity.preferred_username, (identity.email or "").split("@", 1)[0]]
    for candidate in candidates:
        cleaned = re.sub(r"[^a-z0-9._-]", "", (candidate or "").strip().lower())[:32]
        if USERNAME_PATTERN.match(cleaned):
            return cleaned
    return "user"


class OidcFlowError(Exception):
    """Ends a callback with a redirect to `page#error=<code>`."""

    def __init__(self, code: str, page: str = "/login"):
        super().__init__(code)
        self.code = code
        self.page = page


class OidcService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AuthRepository(db)
        self.auth = AuthService(self.repository)

    # --- Start --------------------------------------------------------------

    def start(
        self,
        purpose: str,
        request: Request,
        response: Response,
        *,
        user: User | None = None,
        session_id: int | None = None,
        found: Invite | Invitation | None = None,
        payload: dict | None = None,
        return_to: str | None = None,
    ) -> str:
        """Remember what to do after the provider and return the URL to send the browser to."""
        settings = require_settings()
        ip_address = client_ip(request)
        oidc_rate_limiter.check(ip_address, ip_address)
        oidc_rate_limiter.record_failure(ip_address, ip_address)
        client = client_for(settings)
        now = utcnow()
        self.db.execute(delete(OidcLoginState).where(OidcLoginState.expires_at <= now))
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        verifier, challenge = pkce_pair()
        try:
            url = client.authorization_url(
                state=state,
                nonce=nonce,
                code_challenge=challenge,
                redirect_uri=get_oidc_redirect_uri(),
                reauth=purpose == PURPOSE_REAUTH,
            )
        except OidcError as exc:
            self.db.rollback()
            logger.warning("OIDC provider not usable: %s", exc.message)
            raise AppError(status.HTTP_503_SERVICE_UNAVAILABLE, exc.code, "The provider cannot be reached") from exc
        self.db.add(
            OidcLoginState(
                state_hash=hash_state(state),
                purpose=purpose,
                code_verifier=verifier,
                nonce=nonce,
                user_id=user.id if user is not None else None,
                session_id=session_id,
                invitation_id=found.id if isinstance(found, Invitation) else None,
                invite_id=found.id if isinstance(found, Invite) else None,
                payload=json.dumps(payload) if payload is not None else None,
                return_to=return_to if return_to in RETURN_PATHS else None,
                expires_at=now + STATE_TTL,
                created_at=now,
            )
        )
        self.db.commit()
        session_cookie = cookie_settings()
        response.set_cookie(
            STATE_COOKIE_NAME,
            state,
            max_age=int(STATE_TTL.total_seconds()),
            path=_cookie_path(request),
            secure=session_cookie["secure"],
            httponly=True,
            # Lax (never strict): the cookie must come along on the redirect back from the provider
            samesite="none" if session_cookie["samesite"] == "none" else "lax",
        )
        return url

    # --- Callback -----------------------------------------------------------

    def callback(self, request: Request, code: str | None, state: str | None, error: str | None) -> Response:
        response = RedirectResponse(get_public_url() + "/", status_code=303)
        response.delete_cookie(STATE_COOKIE_NAME, path=_cookie_path(request))
        page = "/login"
        try:
            row = self._take_state(request, state)
            page = _error_page(row)
            if error:
                raise OidcFlowError("oidc_denied" if error in DENIED_ERRORS else "oidc_provider_error", page)
            if not code:
                raise OidcFlowError("oidc_invalid_response", page)
            settings = require_settings()
            try:
                identity = client_for(settings).authenticate(
                    code=code,
                    code_verifier=row.code_verifier,
                    nonce=row.nonce,
                    redirect_uri=get_oidc_redirect_uri(),
                    authenticated_after=row.created_at.replace(tzinfo=UTC).timestamp()
                    if row.purpose == PURPOSE_REAUTH
                    else None,
                )
            except OidcError as exc:
                logger.warning("OIDC login failed: %s", exc.message)
                raise OidcFlowError(exc.code, page) from exc
            target = self._finish(row, identity, request, response)
        except OidcFlowError as exc:
            self.db.rollback()
            if exc.code in COUNTED_ERRORS:
                ip_address = client_ip(request)
                oidc_rate_limiter.record_failure(ip_address, ip_address)
            response.headers["Location"] = f"{get_public_url()}{exc.page}#error={exc.code}"
            return response
        except AppError as exc:
            self.db.rollback()
            response.headers["Location"] = f"{get_public_url()}{page}#error={exc.code}"
            return response
        response.headers["Location"] = get_public_url() + target
        return response

    def _take_state(self, request: Request, state: str | None) -> OidcLoginState:
        cookie = request.cookies.get(STATE_COOKIE_NAME)
        if not state or not cookie or not hmac.compare_digest(state.encode(), cookie.encode()):
            raise OidcFlowError("oidc_state_invalid")
        row = self.db.scalars(select(OidcLoginState).where(OidcLoginState.state_hash == hash_state(state))).first()
        if row is None:
            raise OidcFlowError("oidc_state_invalid")
        # Single use, whatever happens next
        self.db.delete(row)
        self.db.commit()
        if row.expires_at <= utcnow():
            raise OidcFlowError("oidc_state_invalid")
        return row

    def _finish(self, row: OidcLoginState, identity: Identity, request: Request, response: Response) -> str:
        handlers = {
            PURPOSE_LOGIN: self._login,
            PURPOSE_REGISTER: self._register,
            PURPOSE_LINK: self._link,
            PURPOSE_REAUTH: self._reauth,
            PURPOSE_INVITE: self._invite,
            PURPOSE_SETUP: self._setup,
        }
        return handlers[row.purpose](row, identity, request, response)

    # --- Helpers ------------------------------------------------------------

    def find_identity(self, identity: Identity) -> OidcIdentity | None:
        return self.db.scalars(
            select(OidcIdentity).where(OidcIdentity.issuer == identity.issuer, OidcIdentity.subject == identity.subject)
        ).first()

    def _refresh(self, link: OidcIdentity, identity: Identity) -> None:
        link.email = identity.email
        link.preferred_username = identity.preferred_username
        link.last_login_at = utcnow()

    def _attach(self, user: User, identity: Identity, new_account: bool = False) -> OidcIdentity:
        """Link (or re-link) the account to this subject. The caller commits.

        A new account also takes the provider's address; an existing one keeps managing its own.
        """
        existing = self.find_identity(identity)
        if existing is not None and existing.user_id != user.id:
            raise OidcFlowError("oidc_already_linked", "/profile")
        if existing is None:
            self.db.execute(delete(OidcIdentity).where(OidcIdentity.user_id == user.id))
            existing = OidcIdentity(user_id=user.id, issuer=identity.issuer, subject=identity.subject)
            self.db.add(existing)
        self._refresh(existing, identity)
        if new_account:
            self._take_email(user, identity)
        self.db.flush()
        return existing

    def _take_email(self, user: User, identity: Identity) -> None:
        """The provider's address for a new account without one, if the provider confirmed it and it is free.

        fahrma stores confirmed addresses only; an unconfirmed one is never used.
        """
        email = (identity.email or "").strip().lower()
        if user.email or not identity.email_verified or not email or len(email) > 254:
            return
        taken = self.db.scalar(select(func.count()).select_from(User).where(User.email == email, User.id != user.id))
        if not taken:
            user.email = email

    def _sign_in(self, user: User, request: Request, response: Response) -> None:
        logger.info("OIDC login of account %s", user.id)
        self.auth.start_session(user, request, response, auth_method=AUTH_OIDC)

    def _new_account(self, username: str, role: str, payload: dict, identity: Identity) -> User:
        display_name = (payload.get("display_name") or "").strip() or (identity.name or "").strip()[:80] or username
        user = User(
            username=username,
            display_name=display_name,
            password_hash=NO_PASSWORD,
            role=role,
            locale=payload.get("locale"),
        )
        self.db.add(user)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise OidcFlowError("username_taken") from exc
        return user

    def _free_username(self, base: str) -> str:
        if self.repository.get_user_by_username(base) is None:
            return base
        for number in range(2, 1000):
            candidate = f"{base[: 32 - len(str(number)) - 1]}-{number}"
            if self.repository.get_user_by_username(candidate) is None:
                return candidate
        return f"user-{secrets.token_hex(4)}"

    @staticmethod
    def _payload(row: OidcLoginState) -> dict:
        return json.loads(row.payload) if row.payload else {}

    def _not_linked_yet(self, identity: Identity, page: str = "/login") -> None:
        # Checked before a link is used up, so it can be tried with another provider account
        if self.find_identity(identity) is not None:
            raise OidcFlowError("oidc_already_linked", page)

    # --- Purposes -----------------------------------------------------------

    def _login(self, _row, identity: Identity, request: Request, response: Response) -> str:
        link = self.find_identity(identity)
        if link is not None:
            user = link.user
            if not user.is_active:
                logger.info("OIDC login refused: account %s is deactivated", user.id)
                raise OidcFlowError("account_disabled")
            self._refresh(link, identity)
            self._sign_in(user, request, response)
            return "/"
        settings = require_settings()
        if not settings.auto_create:
            logger.info("OIDC login refused: no account for this subject")
            raise OidcFlowError("oidc_no_account")
        if setup_service.needs_setup(self.db):
            raise OidcFlowError("setup_required")
        user = self._new_account(self._free_username(suggest_username(identity)), ROLE_USER, {}, identity)
        self._attach(user, identity, new_account=True)
        self.db.commit()
        self._sign_in(user, request, response)
        return "/"

    def _register(self, row, identity: Identity, request: Request, response: Response) -> str:
        """Open registration through the provider: the account exists right away (the provider vouches)."""
        if get_registration_mode() != "open":
            raise OidcFlowError("registration_closed", "/register")
        if setup_service.needs_setup(self.db):
            raise OidcFlowError("setup_required", "/register")
        if self.find_identity(identity) is not None:
            # Already registered: just log in
            return self._login(row, identity, request, response)
        payload = self._payload(row)
        username = payload.get("username") or self._free_username(suggest_username(identity))
        if self.repository.get_user_by_username(username) is not None:
            raise OidcFlowError("username_taken", "/register")
        user = self._new_account(username, ROLE_USER, payload, identity)
        self._attach(user, identity, new_account=True)
        self.db.commit()
        self._sign_in(user, request, response)
        return "/"

    def _signed_in_user(self, row: OidcLoginState) -> tuple[User, UserSession]:
        user = self.db.get(User, row.user_id) if row.user_id else None
        session = self.db.get(UserSession, row.session_id) if row.session_id else None
        if user is None or not user.is_active or session is None or session.user_id != user.id:
            raise OidcFlowError("session_expired")
        return user, session

    def _link(self, row, identity: Identity, _request: Request, _response: Response) -> str:
        user, _session = self._signed_in_user(row)
        self._attach(user, identity)
        self.db.commit()
        logger.info("Account %s linked to the OIDC provider", user.id)
        return "/profile#oidc=linked"

    def _reauth(self, row, identity: Identity, _request: Request, _response: Response) -> str:
        user, session = self._signed_in_user(row)
        link = self.find_identity(identity)
        if link is None or link.user_id != user.id:
            raise OidcFlowError("oidc_wrong_account", "/profile")
        self._refresh(link, identity)
        session.auth_method = AUTH_OIDC
        session.authenticated_at = utcnow()
        self.db.commit()
        return f"{row.return_to or '/profile'}#reauth=ok"

    def _invite(self, row, identity: Identity, request: Request, response: Response) -> str:
        """A one-time link used through the provider: a new account, or a password-reset link."""
        if row.invitation_id is not None:
            model, row_id = Invitation, row.invitation_id
        elif row.invite_id is not None:
            model, row_id = Invite, row.invite_id
        else:
            raise OidcFlowError("invite_invalid")
        target_id = None
        if model is Invitation:
            invitation = self.db.get(Invitation, row_id)
            target_id = invitation.target_user_id if invitation is not None else None
        existing = self.find_identity(identity)
        # A reset link may re-link the account it belongs to; everything else needs a new subject
        if existing is not None and (target_id is None or existing.user_id != target_id):
            raise OidcFlowError("oidc_already_linked")
        payload = self._payload(row)
        data = InvitationAccept(
            token="-",
            username=payload.get("username"),
            display_name=payload.get("display_name"),
            locale=payload.get("locale"),
        )
        accepted = InvitationService(self.db).accept_external(
            model,
            row_id,
            data,
            request,
            response,
            # Every link but a password reset creates the account
            External(attach=lambda user: self._attach(user, identity, new_account=target_id is None)),
        )
        logger.info("Link used through the OIDC provider (%s)", accepted.kind)
        if accepted.group_id is not None:
            return f"/g/{accepted.group_id}"
        return "/"

    def _setup(self, row, identity: Identity, request: Request, response: Response) -> str:
        payload = self._payload(row)
        with setup_service.setup_lock():
            if not setup_service.needs_setup(self.db):
                raise OidcFlowError("setup_done")
            user = self._new_account(payload.get("username", ""), ROLE_ADMIN, payload, identity)
            self._attach(user, identity, new_account=True)
            self.db.commit()
        setup_service.clear_token()
        self._sign_in(user, request, response)
        return "/"

    # --- Unlink -------------------------------------------------------------

    def unlink(self, user: User, by: str) -> None:
        deleted = self.db.execute(delete(OidcIdentity).where(OidcIdentity.user_id == user.id)).rowcount
        if not deleted:
            raise AppError(status.HTTP_404_NOT_FOUND, "oidc_not_linked", "This account is not linked")
        self.db.commit()
        self.db.expire(user, ["oidc_identity"])
        logger.info("Account %s unlinked from the OIDC provider (by %s)", user.id, by)


def _error_page(row: OidcLoginState) -> str:
    if row.purpose in (PURPOSE_LINK, PURPOSE_REAUTH):
        return "/profile"
    if row.purpose == PURPOSE_REGISTER:
        return "/register"
    return "/login"


# Provider errors that mean "the person said no" or "could not log in"
DENIED_ERRORS = {"access_denied", "login_required", "consent_required", "interaction_required"}
# Errors that count against the per-IP limit
COUNTED_ERRORS = {"oidc_state_invalid", "oidc_invalid_response", "oidc_reauth_failed"}

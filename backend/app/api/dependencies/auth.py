from fastapi import Depends, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.errors import AppError
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.services.auth_service import SESSION_COOKIE_NAME, AuthService


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    session = AuthService(AuthRepository(db)).current_session(request)
    # Lets the device list mark "this device"
    request.state.session_id = session.id
    return session.user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """The logged-in account, or None without a valid session (for public pages)."""
    if not request.cookies.get(SESSION_COOKIE_NAME):
        return None
    try:
        return require_user(request, db)
    except AppError:
        return None


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise AppError(status.HTTP_403_FORBIDDEN, "instance_admin_only", "Only admins of this instance can do this")
    return user

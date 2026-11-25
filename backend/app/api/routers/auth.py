from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.api.dependencies.clock import get_today
from app.config import get_default_timezone_name
from app.db.database import get_db
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import LoginRequest, MeRead, ProfileUpdate, RegisterRequest
from app.services import group_service
from app.services.auth_service import AuthService
from app.services.login_rate_limiter import login_rate_limiter

router = APIRouter()


def me_response(db: Session, user, today: date) -> MeRead:
    return MeRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        locale=user.locale,
        groups=group_service.groups_of(db, user),
        today=today.isoformat(),
        timezone=get_default_timezone_name(),
    )


@router.post("/login", response_model=MeRead)
def login(
    login_in: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    username = login_in.username.lower()
    ip_address = request.client.host if request.client else "unknown"
    login_rate_limiter.check(username, ip_address)
    try:
        user = AuthService(AuthRepository(db)).login(login_in, response)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login_rate_limiter.record_failure(username, ip_address)
        raise
    login_rate_limiter.record_success(username)
    return me_response(db, user, today)


@router.post("/register", response_model=MeRead, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    ip_address = request.client.host if request.client else "unknown"
    login_rate_limiter.check(data.username, ip_address)
    user = group_service.register(db, data, response)
    return me_response(db, user, today)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    AuthService(AuthRepository(db)).logout(request, response)


@router.get("/me", response_model=MeRead)
def me(user=Depends(require_user), db: Session = Depends(get_db), today: date = Depends(get_today)):
    return me_response(db, user, today)


@router.patch("/me", response_model=MeRead)
def update_me(
    data: ProfileUpdate,
    user=Depends(require_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    if data.display_name is not None:
        user.display_name = data.display_name.strip()
    if "locale" in data.model_fields_set:
        user.locale = data.locale
    db.commit()
    return me_response(db, user, today)

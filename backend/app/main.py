from fastapi import Depends, FastAPI

from app import __version__
from app.api.dependencies.auth import require_admin, require_user
from app.api.routers.account import router as account_router
from app.api.routers.admin import router as admin_router
from app.api.routers.auth import router as auth_router
from app.api.routers.cars import router as cars_router
from app.api.routers.entries import expenses_router, fuel_router, trips_router
from app.api.routers.groups import router as groups_router
from app.api.routers.health import router as health_router
from app.api.routers.invitations import router as invitations_router
from app.api.routers.meta import router as meta_router
from app.api.routers.notifications import router as notifications_router
from app.api.routers.oidc import router as oidc_router
from app.api.routers.operator import router as operator_router
from app.api.routers.receipts import router as receipts_router
from app.api.routers.reservations import router as reservations_router
from app.api.routers.settlements import router as settlements_router
from app.api.routers.setup import router as setup_router
from app.config import APP_NAME, api_docs_enabled
from app.middleware.body_limit import limit_body
from app.middleware.csrf import enforce_csrf

# API docs only on request (API_DOCS=true); not public in production
_docs = api_docs_enabled()
app = FastAPI(
    title=f"{APP_NAME} API",
    version=__version__,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
app.middleware("http")(enforce_csrf)
# Registered last, so it runs first: a large body is refused before anything reads it
app.middleware("http")(limit_body)

# Mounted under /api by app.web: /api/v1/groups → /v1/groups here
app.include_router(health_router)
app.include_router(meta_router, prefix="/v1", tags=["meta"])
app.include_router(setup_router, prefix="/v1/setup", tags=["setup"])
app.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
app.include_router(oidc_router, prefix="/v1/auth/oidc", tags=["auth"])
app.include_router(invitations_router, prefix="/v1/invites", tags=["invitations"])
protected = [Depends(require_user)]
app.include_router(account_router, prefix="/v1/account", tags=["account"], dependencies=protected)
app.include_router(notifications_router, prefix="/v1/account", tags=["notifications"], dependencies=protected)
app.include_router(admin_router, prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])
# Bearer token instead of a login; exempt from the CSRF check (see app.middleware.csrf)
app.include_router(operator_router, prefix="/v1/operator", tags=["operator"])
app.include_router(groups_router, prefix="/v1/groups", tags=["groups"], dependencies=protected)
group = "/v1/groups/{group_id}"
app.include_router(cars_router, prefix=f"{group}/cars", tags=["cars"])
app.include_router(trips_router, prefix=f"{group}/trips", tags=["trips"])
app.include_router(fuel_router, prefix=f"{group}/fuel", tags=["fuel"])
app.include_router(expenses_router, prefix=f"{group}/expenses", tags=["expenses"])
app.include_router(receipts_router, prefix=group, tags=["receipts"])
app.include_router(settlements_router, prefix=group, tags=["settlements"])
app.include_router(reservations_router, prefix=f"{group}/reservations", tags=["reservations"])

from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import csrf_enabled, get_allowed_origins
from app.errors import error_body

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "X-Carshare-CSRF"


def _rejected() -> JSONResponse:
    return JSONResponse(status_code=403, content=error_body("csrf_rejected", "Request origin not allowed"))


async def enforce_csrf(request: Request, call_next):
    """Changes need the custom header (not sendable cross-site without CORS) and a trusted origin."""
    if not csrf_enabled() or request.method not in UNSAFE_METHODS:
        return await call_next(request)

    if request.headers.get(CSRF_HEADER) != "1":
        return _rejected()

    origin = request.headers.get("Origin")
    if not origin:
        referer = request.headers.get("Referer")
        if referer:
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"
    if not origin or origin.rstrip("/") not in set(get_allowed_origins()):
        return _rejected()

    return await call_next(request)

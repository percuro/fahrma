import re

from fastapi import Request
from fastapi.responses import JSONResponse

from app.errors import error_body

# Everything except an upload is small JSON; 1 MB leaves room for long notes and big lists
MAX_BODY_BYTES = 1024 * 1024
# Uploads read their body in pieces and stop at their own limit (MAX_IMPORT_BYTES, MAX_RECEIPT_KB)
UPLOAD_PATHS = re.compile(r"^/v1/groups/(import(/check)?|\d+/(fuel|expenses)/\d+/receipts)$")


async def limit_body(request: Request, call_next):
    """Refuse a large body before it is read: FastAPI reads and parses a JSON body before any
    dependency runs. The server enforces Content-Length, so a body cannot be longer than it says.
    A body sent in chunks has no length to check and is refused; browsers, curl and reverse
    proxies send a length."""
    path = request.scope["path"]
    root = request.scope.get("root_path", "")
    if root and path.startswith(root):
        path = path[len(root) :]
    if request.method == "POST" and UPLOAD_PATHS.match(path):
        return await call_next(request)
    length = request.headers.get("Content-Length")
    if length is not None:
        if not length.isdigit() or int(length) > MAX_BODY_BYTES:
            body = error_body("request_too_large", "The request is too large", max_kb=MAX_BODY_BYTES // 1024)
            return JSONResponse(status_code=413, content=body)
    elif "Transfer-Encoding" in request.headers:
        body = error_body("length_required", "Send the request with a Content-Length")
        return JSONResponse(status_code=411, content=body)
    return await call_next(request)

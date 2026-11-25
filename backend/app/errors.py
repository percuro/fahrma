"""Errors with a stable code for the client.

Every error the API raises on purpose carries a machine-readable ``code`` and
``params``; the interface translates them. ``message`` is an English fallback
for API users and logs:

    {"detail": {"code": "trip_overlap", "params": {"start_km": 100, ...}, "message": "..."}}
"""

from fastapi import HTTPException


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, headers: dict | None = None, **params):
        super().__init__(
            status_code=status_code,
            detail={"code": code, "params": params, "message": message},
            headers=headers,
        )
        self.code = code
        self.params = params


def error_body(code: str, message: str, **params) -> dict:
    """Response body for errors produced outside of exception handling (middleware)."""
    return {"detail": {"code": code, "params": params, "message": message}}

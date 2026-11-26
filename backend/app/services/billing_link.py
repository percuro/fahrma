"""Hand-off to the operator's billing: a link from the group page to BILLING_URL.

fahrma itself contains no payment code. A group admin who wants to change the plan is sent
to BILLING_URL (a pricing page, a contact form or the operator's own billing service) with
the group in the fragment, so it never reaches access logs:

    BILLING_URL#group=12&plan=free                       without OPERATOR_TOKEN
    BILLING_URL#group=12&plan=free&token=<signed token>  with OPERATOR_TOKEN

The token says "this account, an admin of this group, asked to change its plan" and is valid
for an hour. It is signed with a key derived from OPERATOR_TOKEN; the billing service hands it
to POST /api/v1/operator/billing-link/verify and gets the group and the person back, so it
never needs to know the token's format. Once paid, it sets the plan through the operator API.
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import status

from app.config import get_billing_url, get_operator_token
from app.errors import AppError
from app.models.group import Group
from app.models.user import User

TOKEN_LIFETIME = timedelta(hours=1)
_VERSION = 1


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _key(operator_token: str) -> bytes:
    # Its own key, so a billing link never doubles as the operator API's bearer token
    return hmac.new(operator_token.encode(), b"fahrma billing link v1", hashlib.sha256).digest()


def _sign(payload: str, operator_token: str) -> str:
    return _b64(hmac.new(_key(operator_token), payload.encode("ascii"), hashlib.sha256).digest())


def create_token(group: Group, user: User, plan_id: str, now: datetime, operator_token: str) -> str:
    expires = int((now + TOKEN_LIFETIME).timestamp())
    body = json.dumps({"v": _VERSION, "g": group.id, "u": user.id, "p": plan_id, "exp": expires}, separators=(",", ":"))
    payload = _b64(body.encode())
    return f"{payload}.{_sign(payload, operator_token)}"


def _invalid() -> AppError:
    return AppError(status.HTTP_400_BAD_REQUEST, "billing_token_invalid", "The link is invalid or has expired")


def verify_token(token: str, now: datetime, operator_token: str) -> dict:
    """The token's content ({"g": group_id, "u": user_id, "p": plan, "exp": unix time}) if valid."""
    payload, _, signature = token.partition(".")
    if not payload or not signature or not hmac.compare_digest(signature, _sign(payload, operator_token)):
        raise _invalid()
    try:
        data = json.loads(_unb64(payload))
    except ValueError as exc:
        raise _invalid() from exc
    if not isinstance(data, dict) or data.get("v") != _VERSION or not isinstance(data.get("exp"), int):
        raise _invalid()
    if data["exp"] <= int(now.timestamp()):
        raise _invalid()
    return data


def billing_link(group: Group, user: User, plan_id: str) -> str:
    base = get_billing_url()
    if base is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "billing_disabled", "Plans cannot be changed in the app here")
    params = {"group": group.id, "plan": plan_id}
    operator_token = get_operator_token()
    if operator_token:
        params["token"] = create_token(group, user, plan_id, datetime.now(UTC), operator_token)
    return f"{base}#{urlencode(params)}"

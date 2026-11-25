"""Idempotency-Key for new entries: a draft sent twice (the answer was lost on a bad connection) is saved once."""

import re
from collections.abc import Callable

from fastapi import Header, status
from sqlalchemy.exc import IntegrityError

from app.errors import AppError
from app.models.idempotency import IdempotencyKey
from app.services.access import GroupContext

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def idempotency_key(key: str | None = Header(default=None, alias="Idempotency-Key")) -> str | None:
    if key is None:
        return None
    if not KEY_PATTERN.fullmatch(key):
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_idempotency_key",
            "Idempotency-Key must have 8-64 characters from A-Z a-z 0-9 _ -",
        )
    return key


def previous(ctx: GroupContext, key: str | None, kind: str) -> int | None:
    """The entity an earlier request with this key created, or None."""
    if key is None:
        return None
    row = (
        ctx.db.query(IdempotencyKey)
        .filter(
            IdempotencyKey.group_id == ctx.group.id, IdempotencyKey.user_id == ctx.user.id, IdempotencyKey.key == key
        )
        .first()
    )
    if row is None:
        return None
    if row.kind != kind:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "idempotency_key_reused",
            "This Idempotency-Key was already used for something else",
        )
    return row.entity_id


def load[T](ctx: GroupContext, entity_id: int, loader: Callable[[GroupContext, int], T]) -> T:
    """The entity of an earlier request; if it has been deleted since, the draft is not saved a second time."""
    try:
        return loader(ctx, entity_id)
    except AppError as error:
        if error.status_code != status.HTTP_404_NOT_FOUND:
            raise
        raise AppError(
            status.HTTP_409_CONFLICT, "already_sent", "This entry was saved earlier and has been deleted since"
        ) from None


def commit(ctx: GroupContext, key: str | None, kind: str, entity_id: int) -> int:
    """Commit the new entity together with its key. Returns the id that counts: if the same key
    arrived twice at the same time, the other request won and its entity is returned."""
    if key is not None:
        ctx.db.add(IdempotencyKey(group_id=ctx.group.id, user_id=ctx.user.id, key=key, kind=kind, entity_id=entity_id))
    try:
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        winner = previous(ctx, key, kind)
        if winner is None:
            raise
        return winner
    return entity_id

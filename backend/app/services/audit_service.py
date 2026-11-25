import json
from datetime import date, datetime

from app.models.audit import AuditEntry
from app.services.access import GroupContext


def _default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value))


def record(ctx: GroupContext, entity: str, entity_id: int, action: str, data: dict | None = None) -> None:
    """Audit entry in the current transaction (the caller commits)."""
    ctx.db.add(
        AuditEntry(
            group_id=ctx.group.id,
            user_id=ctx.user.id,
            entity=entity,
            entity_id=entity_id,
            action=action,
            diff_json=json.dumps(data, default=_default, ensure_ascii=False) if data is not None else None,
        )
    )


def list_entries(ctx: GroupContext, limit: int = 200) -> list[dict]:
    rows = (
        ctx.db.query(AuditEntry)
        .filter(AuditEntry.group_id == ctx.group.id)
        .order_by(AuditEntry.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "action": row.action,
            "diff": json.loads(row.diff_json) if row.diff_json else None,
            "created_at": row.created_at,
        }
        for row in rows
    ]

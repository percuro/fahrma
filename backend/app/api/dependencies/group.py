from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.db.database import get_db
from app.services.access import GroupContext, load_group_context


def require_member(group_id: int, user=Depends(require_user), db: Session = Depends(get_db)) -> GroupContext:
    return load_group_context(db, user, group_id)

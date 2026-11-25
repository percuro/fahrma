from dataclasses import dataclass

from fastapi import status
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models.group import ROLE_ADMIN, Group, Membership
from app.models.user import User


@dataclass
class GroupContext:
    """The logged-in person in the context of one group (from the require_member dependency)."""

    db: Session
    user: User
    group: Group
    membership: Membership

    @property
    def is_admin(self) -> bool:
        return self.membership.role == ROLE_ADMIN

    def require_admin(self) -> None:
        if not self.is_admin:
            raise AppError(status.HTTP_403_FORBIDDEN, "admin_only", "Only group admins can do this")

    def member_ids(self, active_only: bool = False) -> set[int]:
        query = self.db.query(Membership.user_id).filter(Membership.group_id == self.group.id)
        if active_only:
            query = query.filter(Membership.active.is_(True))
        return {row[0] for row in query}

    def require_members(self, *user_ids: int | None) -> None:
        known = self.member_ids()
        for user_id in user_ids:
            if user_id is not None and user_id not in known:
                raise AppError(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "not_a_member", "Person is not a member of the group"
                )


def load_group_context(db: Session, user: User, group_id: int) -> GroupContext:
    membership = (
        db.query(Membership)
        .filter(Membership.group_id == group_id, Membership.user_id == user.id, Membership.active.is_(True))
        .first()
    )
    # 404 instead of 403: other groups must not be detectable
    if membership is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "group_not_found", "Group not found")
    return GroupContext(db=db, user=user, group=membership.group, membership=membership)

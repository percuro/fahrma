from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SecurityEvent(Base):
    """Logins and changes to accounts, for instance admins and the account itself.

    Usernames are copied, so an entry stays readable after the account is deleted (anonymized).
    """

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)
    event: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # Who did it: None for the command line, the operator API, the system or a stranger
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Whose account it concerns
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Shortened (IPv4 /24, IPv6 /48), and only for failed attempts and blocks
    ip_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Small JSON object; never passwords, tokens or links
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

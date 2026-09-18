# database/models.py
# The Step 3 schema: `users` (who this person is in WorldWalker) and
# `google_health_connections` (what access we currently have to their
# Google Health/Fitbit data) are deliberately separate tables - identity
# vs. volatile, security-sensitive credential state. See docs/prompt_log/
# for the full design conversation.
#
# One table per provider, not a shared "connections" table with a
# provider discriminator - a second provider (e.g. Apple Health) would
# get its own apple_health_connections table once its real shape is
# known, matching services/google_health/'s own isolation. See
# tests/test_database_models.py for what these constraints actually
# guarantee.

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from database.encryption import EncryptedString


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    google_health_connection: Mapped["GoogleHealthConnection | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class GoogleHealthConnection(Base):
    __tablename__ = "google_health_connections"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disconnected')", name="ck_google_health_connections_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # UNIQUE, not just indexed: encodes "one connection per user, ever" -
    # not a history of connection attempts. See the Step 3 design notes
    # for the migration path if that ever needs to change.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Google's own stable id for the account (healthUserId, from
    # users.me.identity) - the key that makes reconnect work: look this
    # up first, and it tells you whether this is a brand new connection
    # or an existing one being re-established.
    provider_user_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # Nullable - disconnecting a connection nulls these out rather than
    # leaving a live credential sitting next to a status flag someone
    # could forget to check. EncryptedString (database/encryption.py):
    # encrypted before every write, decrypted on every read - callers
    # here and in application code just see plain strings.
    access_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

    # Absolute timestamp, not obtained_at + expires_in - checking
    # staleness is just now() > token_expires_at, no arithmetic scattered
    # through the codebase.
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scopes: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="google_health_connection")

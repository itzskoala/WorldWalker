# database/models.py

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.database.encryption import EncryptedString


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)

    google_sub: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Profile page fields.
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    f_name: Mapped[str | None] = mapped_column(String, nullable=True)
    l_name: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_photo: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str | None] = mapped_column(String, nullable=True)

    lifetime_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    postcards_sum: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    member_since: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    google_health_connection: Mapped["GoogleHealthConnection | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    trips: Mapped[list["ActiveTrip"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class GoogleHealthConnection(Base):
    __tablename__ = "google_health_connections"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disconnected')", name="ck_google_health_connections_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    provider_user_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    access_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scopes: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="google_health_connection")


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String, primary_key=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActiveTrip(Base):
    __tablename__ = "active_trips"

    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'completed', 'abandoned')", name="ck_active_trips_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default="active")

    from_place: Mapped[str] = mapped_column(String, nullable=False)
    to_place: Mapped[str] = mapped_column(String, nullable=False)

    start_lat: Mapped[float] = mapped_column(Float, nullable=False)
    start_lng: Mapped[float] = mapped_column(Float, nullable=False)
    end_lat: Mapped[float] = mapped_column(Float, nullable=False)
    end_lng: Mapped[float] = mapped_column(Float, nullable=False)

    route_geometry: Mapped[list] = mapped_column(JSON, nullable=False)
    total_distance_m: Mapped[float] = mapped_column(Float, nullable=False)

    meters_walked: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")

    stride_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    stride_by_type: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    workout_intervals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    milestones_notified: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    checkpoint_reveal_radius_m: Mapped[float] = mapped_column(Float, nullable=False, default=75.0, server_default="75")

    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_paused_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="trips")
    checkpoints: Mapped[list["TripCheckpoint"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripCheckpoint.checkpoint_number"
    )


class EmailNotificationConfig(Base):
    __tablename__ = "email_notification_configs"

    # One per user (like GoogleHealthConnection) - WorldWalker never holds
    # a shared platform sender account. This IS the user's own SMTP
    # account (e.g. a Gmail address + app password); checkpoint emails are
    # sent from and to this same address using their own credentials.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    smtp_host: Mapped[str] = mapped_column(String, nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False)

    # EncryptedString (backend/database/encryption.py): encrypted before
    # every write, decrypted on every read - same pattern as
    # GoogleHealthConnection's access_token/refresh_token above.
    smtp_username: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    smtp_password: Mapped[str] = mapped_column(EncryptedString, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StepSyncLog(Base):
    __tablename__ = "step_sync_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("active_trips.id", ondelete="CASCADE"), nullable=False, index=True
    )

    steps: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_walked_miles: Mapped[float] = mapped_column(Float, nullable=False)
    distance_remaining_miles: Mapped[float] = mapped_column(Float, nullable=False)
    percent_complete: Mapped[float] = mapped_column(Float, nullable=False)

    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TripCheckpoint(Base):
    __tablename__ = "trip_checkpoints"

    __table_args__ = (
        CheckConstraint(
            "metadata_status IN ('pending', 'processing', 'ready')", name="ck_trip_checkpoints_metadata_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("active_trips.id", ondelete="CASCADE"), nullable=False
    )

    checkpoint_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    distance_from_start_m: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")


    metadata_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    metadata_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trip: Mapped["ActiveTrip"] = relationship(back_populates="checkpoints")


class PlaceRecord(Base):
    __tablename__ = "places"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False, default="")
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    search_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

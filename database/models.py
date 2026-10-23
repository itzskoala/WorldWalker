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
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from database.encryption import EncryptedString


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Nullable: rows written before accounts/service.py's signup existed
    # have neither - a WorldWalker login (email/password) is required for
    # every new user now, including one about to connect Google Health
    # (see auth/connections.py - it only ever links an existing user, it
    # never creates one).
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String, nullable=True)

    # Google's stable per-account identifier (the ID token's "sub" claim,
    # see accounts/google_oauth.py) for a user who signed up/in with
    # "Sign in with Google". UNIQUE so the same Google account always
    # resolves back to one WorldWalker user - accounts/service.py's
    # signup_or_login_google() looks up by this first, before ever
    # touching email, so a returning Google user is found even if they've
    # since changed their email with Google. Nullable: unrelated to
    # hashed_password - a user can have either, or both (an email/password
    # account that later linked Google, see signup_or_login_google()).
    google_sub: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Profile page fields.
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    f_name: Mapped[str | None] = mapped_column(String, nullable=True)
    l_name: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_photo: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str | None] = mapped_column(String, nullable=True)

    # Persisted running totals, not computed - they need to survive a
    # trip (and its step_sync_log/postcard rows) being deleted.
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

    # UNIQUE, not just indexed: encodes "one connection per user, ever" -
    # not a history of connection attempts. See the Step 3 design notes
    # for the migration path if that ever needs to change.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Google's own stable id for the account (healthUserId, from
    # users.me.identity) - UNIQUE so one Google account can never be
    # linked to two different WorldWalker users. Which WorldWalker user a
    # connection belongs to is always user_id above, resolved from our
    # own login (OAuth state, see auth/google_health_auth.py), never from
    # this column - this is only how an incoming webhook notification
    # (which only ever carries Google's own identity) maps back to one.
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


class OAuthState(Base):
    __tablename__ = "oauth_states"

    # The random token itself (secrets.token_urlsafe(32) - see
    # auth/oauth_state.py) is the primary key, not a separate id - it's
    # already a unique, unguessable identifier, and this table is looked
    # up by nothing else. Shared across every worker/process via
    # Postgres instead of an in-process dict, since a real deployment
    # runs more than one Uvicorn worker - a state issued by one worker
    # must be consumable by whichever worker handles the callback.
    state: Mapped[str] = mapped_column(String, primary_key=True)

    # Which WorldWalker user this OAuth flow is for - recovered on
    # callback instead of trusting anything Google or the client sends.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Short-lived and single-use: auth/oauth_state.py's consume_state()
    # deletes the row the moment it's read, valid or not - a stale,
    # never-consumed row past this timestamp is also opportunistically
    # cleaned up the next time a state is issued. No other data belongs
    # here - the state token and who it's for is all a CSRF check needs.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActiveTrip(Base):
    __tablename__ = "active_trips"

    # A user can have several trips going at once (see database/trips.py) -
    # a trip is being walked right now ("active"), temporarily not accruing
    # real steps ("paused"), or was walked all the way to its destination
    # ("completed"). "abandoned" is kept only for rows written before
    # multi-trip support; nothing sets it anymore - trips.delete_trip() now
    # hard-deletes the row (and its checkpoints, via cascade) instead.
    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'completed', 'abandoned')", name="ck_active_trips_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default="active")

    # What the user actually typed, kept for display (the map header, the
    # "you reached X!" finished message) - separate from the geocoded
    # coordinates below, which are what the map and the progress math use.
    from_place: Mapped[str] = mapped_column(String, nullable=False)
    to_place: Mapped[str] = mapped_column(String, nullable=False)

    start_lat: Mapped[float] = mapped_column(Float, nullable=False)
    start_lng: Mapped[float] = mapped_column(Float, nullable=False)
    end_lat: Mapped[float] = mapped_column(Float, nullable=False)
    end_lng: Mapped[float] = mapped_column(Float, nullable=False)

    # The ordered list of {"lat": ..., "lng": ...} points OSRM returned for
    # this route (see travel_logic/route_service.py's Route.points). Storing
    # the whole polyline - not just start/end - means get_map_state() can
    # redraw the full route line and re-run locate_on_route() on every
    # request without calling OSRM again.
    route_geometry: Mapped[list] = mapped_column(JSON, nullable=False)
    total_distance_m: Mapped[float] = mapped_column(Float, nullable=False)

    # The one field that actually changes after the trip is created - every
    # other column here is trip setup, written once. Grows only through
    # database/trips.py's add_progress(), called from
    # TravelFacade.record_steps()/record_workout().
    meters_walked: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")

    # Per-trip walking config, seeded once at start_journey() time - same
    # fields travel_logic/progress_calculator.py's resolve_stride_m() and
    # workout_distance_m() already take as arguments, just persisted here
    # instead of living in a process-local dict.
    stride_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    stride_by_type: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # (start_time, end_time) pairs record_workout() already credited, so a
    # later "steps" event covering the same window doesn't double-count it -
    # see progress_calculator.interval_within_any().
    workout_intervals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Which of {"halfway", "finished"} have already fired an Observer event
    # for this trip, so milestones_just_crossed() never re-fires one.
    milestones_notified: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    round_trip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Randomized once, at trip creation (travel_logic/checkpoints.py's
    # generate_reveal_radius_m(), a uniform 50-100m draw), and never
    # re-rolled afterward - every TripCheckpoint on this trip reveals
    # itself (see TripCheckpoint.revealed_at) once the walker's
    # distance_walked_m comes within this many meters of it, and stays
    # revealed for the rest of the trip. server_default backfills every
    # pre-existing trip to the range's midpoint rather than leaving it
    # null, since nullable=False here means every trip has a real radius.
    checkpoint_reveal_radius_m: Mapped[float] = mapped_column(Float, nullable=False, default=75.0, server_default="75")

    # When status is "paused", the moment that started - used, together
    # with total_paused_seconds below, to keep "elapsed_seconds" meaning
    # "time actually walking" rather than "wall-clock time since started_at"
    # (see core/facade.py's _build_map_state()). Cleared back to null on
    # resume, once its duration has been folded into total_paused_seconds.
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
    # sent from and to this same address using their own credentials -
    # see core/observer_decorator/email_alerts_listener.py.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    smtp_host: Mapped[str] = mapped_column(String, nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False)

    # EncryptedString (database/encryption.py): encrypted before every
    # write, decrypted on every read - same pattern as
    # GoogleHealthConnection's access_token/refresh_token above.
    smtp_username: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    smtp_password: Mapped[str] = mapped_column(EncryptedString, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StepSyncLog(Base):
    __tablename__ = "step_sync_log"

    # One row per (trip, Fitbit/Google Health sync) pair - what used to
    # live in data/total_distance_db.py's SQLite file (total_distance.db).
    # Moved here because Vercel's filesystem is read-only in production
    # (no local SQLite writes survive past a single invocation); Postgres
    # is the one persistent store this app has. total_steps/today_steps/
    # lifetime_steps are still SUMs over this log, not separately-stored
    # counters - see data/total_distance_db.py.
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

    # Stored tz-aware (unlike the old SQLite column, a plain ISO string) -
    # today_steps() still does its own UTC day-boundary math in Python
    # rather than trusting the DB session's timezone, so "today" means the
    # same thing it always did.
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

    # Every checkpoint's position for the whole route is generated and
    # persisted up front, in one shot, at trip creation (travel_logic/
    # checkpoints.py's generate_checkpoint_positions(), called from
    # database/trips.py's create_trip()) - checkpoint_number/lat/lng/
    # distance_from_start_m are all real from the instant this row exists
    # and never change afterward. name/description start blank - see
    # metadata_status below.
    checkpoint_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    distance_from_start_m: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")

    # "pending" the instant this row is written (name/description both
    # still blank). A background job claims a checkpoint by flipping this
    # to "processing" (database/trips.py's claim_checkpoint_for_metadata())
    # right before resolving its real name/description, then "ready" once
    # both are persisted (set_checkpoint_metadata()) - or back to
    # "pending" on failure, so a later call retries it. core/facade.py
    # only ever resolves metadata for checkpoints the walker is actually
    # near (plus a small lookahead buffer), not every checkpoint at once -
    # most of a long route's checkpoints sit "pending" for a long time,
    # by design.
    metadata_status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    # Set the moment a job claims this checkpoint (see metadata_status
    # above) - lets a later claim attempt tell a genuinely stuck
    # "processing" row (its worker crashed or never ran) from one that's
    # actively being worked on right now, and safely retry the former.
    metadata_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Null until the walker's distance_walked_m comes within the trip's
    # own checkpoint_reveal_radius_m of this checkpoint; set once and
    # never cleared after that - a checkpoint reveals itself a little
    # before the walker actually reaches it (that's the whole point of
    # the radius) and then stays visible on the map for the rest of the
    # trip, however far ahead the walker gets. Deliberately independent
    # of metadata_status: a checkpoint can be revealed before its name is
    # known (the map shows it immediately; the label fills in once
    # resolve_checkpoint_name() finishes) - see core/facade.py.
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Null until the trip's meters_walked passes distance_from_start_m; set
    # once and never cleared after that. Same idea as
    # data/landmarks_db.py's old "notified" flag, now relational and scoped
    # to the trip that generated it instead of a SQLite row keyed by a raw
    # user_id string.
    hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trip: Mapped["ActiveTrip"] = relationship(back_populates="checkpoints")

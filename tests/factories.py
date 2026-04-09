"""
All test-data builders in one place.
Import from here in every test file — never define dummy data inline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from app.deps import CurrentUser
from app.scopes import BookingScope

# ---------------------------------------------------------------------------
# Stable IDs — use these when a specific, repeatable UUID is needed.
# Call uuid4() inline when you need a fresh one per test.
# ---------------------------------------------------------------------------

CUSTOMER_ID: UUID = uuid4()
PROPERTY_OWNER_ID: UUID = uuid4()
ADMIN_ID: UUID = uuid4()
OTHER_USER_ID: UUID = uuid4()

BOOKING_ID: UUID = uuid4()
PROPERTY_ID: UUID = uuid4()

NOW = datetime(2026, 6, 1, 14, 0, 0, tzinfo=UTC)  # used for updated_at timestamps
START_DATE = date(2026, 6, 1)
END_DATE = date(2026, 6, 3)  # 2-night stay


# ---------------------------------------------------------------------------
# User factories
# ---------------------------------------------------------------------------


def make_customer(
    user_id: UUID = CUSTOMER_ID,
    scopes: list[str] | None = None,
) -> CurrentUser:
    """Customer with read/write/cancel booking scopes and properties:read."""
    if scopes is None:
        scopes = [
            BookingScope.READ,
            BookingScope.WRITE,
            BookingScope.CANCEL,
            "properties:read",
        ]
    return CurrentUser(id=user_id, username=f"customer_{user_id}", scopes=scopes)


def make_property_owner(
    user_id: UUID = PROPERTY_OWNER_ID,
    scopes: list[str] | None = None,
) -> CurrentUser:
    """Property owner with manage booking scope and properties:read."""
    if scopes is None:
        scopes = [
            BookingScope.MANAGE,
            "properties:read",
        ]
    return CurrentUser(id=user_id, username=f"owner_{user_id}", scopes=scopes)


def make_admin() -> CurrentUser:
    """Admin with all admin:bookings:* scopes."""
    return CurrentUser(
        id=ADMIN_ID,
        username="admin",
        scopes=[
            "admin:scopes",
            "properties:read",
            BookingScope.READ,
            BookingScope.ADMIN,
            BookingScope.ADMIN_READ,
            BookingScope.ADMIN_WRITE,
            BookingScope.ADMIN_DELETE,
        ],
    )


# ---------------------------------------------------------------------------
# Response dict factories  (mirror what the CRUD layer returns as dicts)
# ---------------------------------------------------------------------------


def booking_response(**overrides) -> dict:
    base = dict(
        id=str(BOOKING_ID),
        property_id=str(PROPERTY_ID),
        property_owner_id=str(PROPERTY_OWNER_ID),
        user_id=str(CUSTOMER_ID),
        start_date=START_DATE.isoformat(),
        end_date=END_DATE.isoformat(),
        status="pending",
        price_per_night="50.00",
        total_price="100.00",
        currency="EUR",
        guest_name=None,
        guest_email=None,
        guest_phone=None,
        special_requests=None,
        updated_at=NOW.isoformat(),
    )
    return {**base, **overrides}


def property_dict(**overrides) -> dict:
    """Minimal properties-ms property representation used by PropertiesClient mocks."""
    base = dict(
        id=str(PROPERTY_ID),
        owner_id=str(PROPERTY_OWNER_ID),
        name="Test Property",
        status="active",
        price_per_night="50.00",
        currency="EUR",
    )
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# Request payload factories
# ---------------------------------------------------------------------------


def user_dict(user_id: UUID = CUSTOMER_ID, **overrides) -> dict:
    """Minimal users-ms user representation used by UsersClient mocks."""
    base = dict(
        id=str(user_id),
        username=f"user_{str(user_id)[:8]}",
        full_name="Test User",
        email="test@example.com",
        is_active=True,
        scopes=[],
        created_at=NOW.isoformat(),
    )
    return {**base, **overrides}


def booking_create_payload(**overrides) -> dict:
    base = dict(
        property_id=str(PROPERTY_ID),
        start_date=START_DATE.isoformat(),
        end_date=END_DATE.isoformat(),
        guest_name=None,
        guest_email=None,
        guest_phone=None,
        special_requests=None,
    )
    return {**base, **overrides}

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.checkin_dispatch import maybe_send_checkin_link
from app.models import Booking, BookingStatus

from .factories import CUSTOMER_ID, PROPERTY_ID, PROPERTY_OWNER_ID


@pytest.fixture(autouse=True)
async def _init_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


def _clients() -> tuple[MagicMock, MagicMock]:
    users_client = MagicMock()
    users_client.get_by_ids = AsyncMock(
        return_value=[{"id": str(CUSTOMER_ID), "email": "guest@example.com"}]
    )
    notifications_client = MagicMock()
    notifications_client.send = AsyncMock(return_value=None)
    return users_client, notifications_client


async def _make_booking(**overrides) -> Booking:
    base = dict(
        property_id=PROPERTY_ID,
        property_owner_id=PROPERTY_OWNER_ID,
        user_id=CUSTOMER_ID,
        start_date=date.today() + timedelta(days=1),
        end_date=date.today() + timedelta(days=3),
        price_per_night="50.00",
        total_price="100.00",
        status=BookingStatus.CONFIRMED,
    )
    return await Booking.create(**{**base, **overrides})


async def test_sends_link_for_confirmed_booking_inside_window_and_marks_sent():
    booking = await _make_booking()
    users_client, notifications_client = _clients()

    await maybe_send_checkin_link(booking.id, users_client, notifications_client)

    notifications_client.send.assert_awaited_once()
    await booking.refresh_from_db()
    assert booking.checkin_link_sent_at is not None


async def test_skips_booking_outside_lead_window():
    booking = await _make_booking(
        start_date=date.today() + timedelta(days=10),
        end_date=date.today() + timedelta(days=12),
    )
    users_client, notifications_client = _clients()

    await maybe_send_checkin_link(booking.id, users_client, notifications_client)

    notifications_client.send.assert_not_awaited()
    await booking.refresh_from_db()
    assert booking.checkin_link_sent_at is None


async def test_skips_non_confirmed_booking():
    booking = await _make_booking(status=BookingStatus.PENDING)
    users_client, notifications_client = _clients()

    await maybe_send_checkin_link(booking.id, users_client, notifications_client)

    notifications_client.send.assert_not_awaited()


async def test_is_idempotent_when_link_already_sent():
    booking = await _make_booking(checkin_link_sent_at=datetime.now(UTC))
    users_client, notifications_client = _clients()

    await maybe_send_checkin_link(booking.id, users_client, notifications_client)

    notifications_client.send.assert_not_awaited()


async def test_noop_when_booking_missing():
    users_client, notifications_client = _clients()

    await maybe_send_checkin_link(uuid4(), users_client, notifications_client)

    notifications_client.send.assert_not_awaited()


async def test_marks_sent_even_when_guest_has_no_email():
    booking = await _make_booking()
    users_client, notifications_client = _clients()
    users_client.get_by_ids = AsyncMock(return_value=[])

    await maybe_send_checkin_link(booking.id, users_client, notifications_client)

    notifications_client.send.assert_not_awaited()
    await booking.refresh_from_db()
    assert booking.checkin_link_sent_at is not None

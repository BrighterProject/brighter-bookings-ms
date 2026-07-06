from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from tortoise import Tortoise

from app.checkin_token import generate_checkin_token
from app.deps import (
    can_view_guest_identities,
    get_booking_from_checkin_token,
    verify_internal_cron_secret,
)
from app.models import Booking

from .factories import (
    CUSTOMER_ID,
    END_DATE,
    PROPERTY_ID,
    PROPERTY_OWNER_ID,
    START_DATE,
    make_admin,
    make_customer,
    make_property_owner,
)


@pytest.fixture(autouse=True)
async def _init_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def _make_booking() -> Booking:
    return await Booking.create(
        property_id=PROPERTY_ID,
        property_owner_id=PROPERTY_OWNER_ID,
        user_id=CUSTOMER_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        price_per_night="50.00",
        total_price="100.00",
    )


async def test_get_booking_from_checkin_token_returns_booking():
    booking = await _make_booking()
    token = generate_checkin_token(booking.id, end_date=date.today() + timedelta(days=5))
    resolved = await get_booking_from_checkin_token(token)
    assert resolved.id == booking.id


async def test_get_booking_from_checkin_token_rejects_garbage_token():
    with pytest.raises(HTTPException) as exc_info:
        await get_booking_from_checkin_token("not-a-real-token")
    assert exc_info.value.status_code == 401


async def test_get_booking_from_checkin_token_404s_on_deleted_booking():
    token = generate_checkin_token(uuid4(), end_date=date.today() + timedelta(days=5))
    with pytest.raises(HTTPException) as exc_info:
        await get_booking_from_checkin_token(token)
    assert exc_info.value.status_code == 404


async def test_can_view_guest_identities_allows_host():
    booking = await _make_booking()
    result = await can_view_guest_identities(
        booking_id=booking.id, current_user=make_property_owner()
    )
    assert result.id == booking.id


async def test_can_view_guest_identities_allows_admin():
    booking = await _make_booking()
    result = await can_view_guest_identities(booking_id=booking.id, current_user=make_admin())
    assert result.id == booking.id


async def test_can_view_guest_identities_rejects_unrelated_customer():
    booking = await _make_booking()
    with pytest.raises(HTTPException) as exc_info:
        await can_view_guest_identities(booking_id=booking.id, current_user=make_customer())
    assert exc_info.value.status_code == 403


async def test_can_view_guest_identities_rejects_other_hosts():
    booking = await _make_booking()
    other_host = make_property_owner(user_id=uuid4())
    with pytest.raises(HTTPException) as exc_info:
        await can_view_guest_identities(booking_id=booking.id, current_user=other_host)
    assert exc_info.value.status_code == 403


async def test_verify_internal_cron_secret_accepts_correct_bearer(monkeypatch):
    monkeypatch.setattr("app.settings.internal_cron_secret", "shh")
    await verify_internal_cron_secret(authorization="Bearer shh")  # does not raise


async def test_verify_internal_cron_secret_rejects_wrong_or_missing(monkeypatch):
    monkeypatch.setattr("app.settings.internal_cron_secret", "shh")
    with pytest.raises(HTTPException) as exc_info:
        await verify_internal_cron_secret(authorization="Bearer wrong")
    assert exc_info.value.status_code == 401
    with pytest.raises(HTTPException):
        await verify_internal_cron_secret(authorization="")

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app import settings
from app.deps import get_notifications_client, get_users_client
from app.models import Booking, BookingStatus, DocumentType, Gender, GuestIdentity
from app.routers.internal_checkin import router

from .factories import CUSTOMER_ID, PROPERTY_ID, PROPERTY_OWNER_ID

_HEADERS = {"Authorization": "Bearer shh"}


@pytest.fixture(autouse=True)
async def _init_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.fixture(autouse=True)
def _cron_secret(monkeypatch):
    monkeypatch.setattr(settings, "internal_cron_secret", "shh")


def _app() -> tuple[FastAPI, MagicMock, MagicMock]:
    app = FastAPI()
    app.include_router(router)

    users_client = MagicMock()
    users_client.get_by_ids = AsyncMock(
        return_value=[{"id": str(CUSTOMER_ID), "email": "guest@example.com"}]
    )
    notifications_client = MagicMock()
    notifications_client.send = AsyncMock(return_value=None)

    app.dependency_overrides[get_users_client] = lambda: users_client
    app.dependency_overrides[get_notifications_client] = lambda: notifications_client
    return app, users_client, notifications_client


def _http(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_dispatch_requires_the_shared_secret():
    app, _, _ = _app()
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/dispatch")
    assert resp.status_code == 401


async def test_dispatch_sends_link_for_booking_inside_lead_window_and_marks_sent():
    app, _, notifications_client = _app()
    booking = await Booking.create(
        property_id=PROPERTY_ID, property_owner_id=PROPERTY_OWNER_ID, user_id=CUSTOMER_ID,
        start_date=date.today() + timedelta(days=1), end_date=date.today() + timedelta(days=3),
        price_per_night="50.00", total_price="100.00", status=BookingStatus.CONFIRMED,
    )
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/dispatch", headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["dispatched"] == 1
    notifications_client.send.assert_awaited_once()
    await booking.refresh_from_db()
    assert booking.checkin_link_sent_at is not None


async def test_dispatch_skips_booking_outside_lead_window():
    app, _, notifications_client = _app()
    await Booking.create(
        property_id=PROPERTY_ID, property_owner_id=PROPERTY_OWNER_ID, user_id=CUSTOMER_ID,
        start_date=date.today() + timedelta(days=10), end_date=date.today() + timedelta(days=12),
        price_per_night="50.00", total_price="100.00", status=BookingStatus.CONFIRMED,
    )
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/dispatch", headers=_HEADERS)
    assert resp.json()["dispatched"] == 0
    notifications_client.send.assert_not_awaited()


async def test_dispatch_skips_non_confirmed_bookings():
    app, _, notifications_client = _app()
    await Booking.create(
        property_id=PROPERTY_ID, property_owner_id=PROPERTY_OWNER_ID, user_id=CUSTOMER_ID,
        start_date=date.today() + timedelta(days=1), end_date=date.today() + timedelta(days=3),
        price_per_night="50.00", total_price="100.00", status=BookingStatus.CANCELLED,
    )
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/dispatch", headers=_HEADERS)
    assert resp.json()["dispatched"] == 0
    notifications_client.send.assert_not_awaited()


async def test_dispatch_is_idempotent_and_skips_already_sent():
    app, _, notifications_client = _app()
    await Booking.create(
        property_id=PROPERTY_ID, property_owner_id=PROPERTY_OWNER_ID, user_id=CUSTOMER_ID,
        start_date=date.today() + timedelta(days=1), end_date=date.today() + timedelta(days=3),
        price_per_night="50.00", total_price="100.00", status=BookingStatus.CONFIRMED,
        checkin_link_sent_at=datetime.now(UTC),
    )
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/dispatch", headers=_HEADERS)
    assert resp.json()["dispatched"] == 0
    notifications_client.send.assert_not_awaited()


async def test_purge_requires_the_shared_secret():
    app, _, _ = _app()
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/purge")
    assert resp.status_code == 401


async def test_purge_strips_everything_but_names_past_the_window():
    app, _, _ = _app()
    booking = await Booking.create(
        property_id=PROPERTY_ID, property_owner_id=PROPERTY_OWNER_ID, user_id=CUSTOMER_ID,
        start_date=date.today() - timedelta(days=40), end_date=date.today() - timedelta(days=38),
        price_per_night="50.00", total_price="100.00", status=BookingStatus.COMPLETED,
    )
    guest = await GuestIdentity.create(
        booking=booking, first_name="Ivan", middle_name="Petrov", last_name="Ivanov",
        date_of_birth=date(1980, 1, 1), gender=Gender.MALE, citizenship="BG",
        document_type=DocumentType.ID_CARD, document_number="123456789",
        document_issuing_country="BG", pin_egn="8001010034",
    )
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/purge", headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["purged_bookings"] == 1

    await guest.refresh_from_db()
    assert guest.first_name == "Ivan"
    assert guest.middle_name == "Petrov"
    assert guest.last_name == "Ivanov"
    assert guest.document_number is None
    assert guest.pin_egn is None
    assert guest.date_of_birth is None
    assert guest.gender is None
    assert guest.citizenship is None
    assert guest.document_type is None
    assert guest.document_issuing_country is None

    await booking.refresh_from_db()
    assert booking.guest_data_purged_at is not None


async def test_purge_skips_bookings_still_inside_the_window():
    app, _, _ = _app()
    booking = await Booking.create(
        property_id=PROPERTY_ID, property_owner_id=PROPERTY_OWNER_ID, user_id=CUSTOMER_ID,
        start_date=date.today() - timedelta(days=5), end_date=date.today() - timedelta(days=3),
        price_per_night="50.00", total_price="100.00", status=BookingStatus.COMPLETED,
    )
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/purge", headers=_HEADERS)
    assert resp.json()["purged_bookings"] == 0
    await booking.refresh_from_db()
    assert booking.guest_data_purged_at is None


async def test_purge_is_idempotent_and_skips_already_purged():
    app, _, _ = _app()
    await Booking.create(
        property_id=PROPERTY_ID, property_owner_id=PROPERTY_OWNER_ID, user_id=CUSTOMER_ID,
        start_date=date.today() - timedelta(days=40), end_date=date.today() - timedelta(days=38),
        price_per_night="50.00", total_price="100.00", status=BookingStatus.COMPLETED,
        guest_data_purged_at=datetime.now(UTC),
    )
    async with _http(app) as client:
        resp = await client.post("/internal/checkin/purge", headers=_HEADERS)
    assert resp.json()["purged_bookings"] == 0

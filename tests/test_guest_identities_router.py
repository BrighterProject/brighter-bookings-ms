from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.deps import get_current_user
from app.limiter import limiter
from app.models import Booking, BookingStatus, DocumentType, Gender, GuestIdentity
from app.routers.guest_identities import router

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


@pytest.fixture()
async def booking() -> Booking:
    return await Booking.create(
        property_id=PROPERTY_ID,
        property_owner_id=PROPERTY_OWNER_ID,
        user_id=CUSTOMER_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        price_per_night="50.00",
        total_price="100.00",
        num_guests=2,
    )


def _client(current_user) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)
    app.state.limiter = limiter

    async def _user():
        return current_user

    app.dependency_overrides[get_current_user] = _user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _guest_payload(**overrides):
    base = dict(
        first_name="Ivan",
        middle_name="Petrov",
        last_name="Ivanov",
        date_of_birth="1980-01-01",
        gender="male",
        citizenship="BG",
        document_type="id_card",
        document_number="123456789",
        document_issuing_country="BG",
        pin_egn="8001010034",
    )
    return {**base, **overrides}


async def _seed_guest(booking: Booking) -> GuestIdentity:
    return await GuestIdentity.create(
        booking=booking,
        first_name="Ivan",
        middle_name="Petrov",
        last_name="Ivanov",
        date_of_birth=date(1980, 1, 1),
        gender=Gender.MALE,
        citizenship="BG",
        document_type=DocumentType.ID_CARD,
        document_number="123456789",
        document_issuing_country="BG",
        pin_egn="8001010034",
    )


async def test_admin_can_add_guest(booking):
    async with _client(make_admin()) as client:
        resp = await client.post(f"/bookings/{booking.id}/guests", json=_guest_payload())
    assert resp.status_code == 201
    assert resp.json()["document_number"] == "123456789"


async def test_non_admin_cannot_add_guest(booking):
    async with _client(make_customer()) as client:
        resp = await client.post(f"/bookings/{booking.id}/guests", json=_guest_payload())
    assert resp.status_code == 403


async def test_admin_cannot_add_guest_to_cancelled_booking(booking):
    booking.status = BookingStatus.CANCELLED
    await booking.save(update_fields=["status"])
    async with _client(make_admin()) as client:
        resp = await client.post(f"/bookings/{booking.id}/guests", json=_guest_payload())
    assert resp.status_code == 422


async def test_host_sees_full_decrypted_roster(booking):
    await _seed_guest(booking)
    async with _client(make_property_owner(user_id=PROPERTY_OWNER_ID)) as client:
        resp = await client.get(f"/bookings/{booking.id}/guests")
    assert resp.status_code == 200
    assert resp.json()[0]["document_number"] == "123456789"
    assert resp.json()[0]["pin_egn"] == "8001010034"


async def test_admin_sees_full_decrypted_roster(booking):
    await _seed_guest(booking)
    async with _client(make_admin()) as client:
        resp = await client.get(f"/bookings/{booking.id}/guests")
    assert resp.status_code == 200
    assert resp.json()[0]["pin_egn"] == "8001010034"


async def test_unrelated_customer_gets_403(booking):
    async with _client(make_customer(user_id=uuid4())) as client:
        resp = await client.get(f"/bookings/{booking.id}/guests")
    assert resp.status_code == 403


async def test_other_property_owners_get_403(booking):
    async with _client(make_property_owner(user_id=uuid4())) as client:
        resp = await client.get(f"/bookings/{booking.id}/guests")
    assert resp.status_code == 403


async def test_admin_can_delete_guest(booking):
    guest = await _seed_guest(booking)
    async with _client(make_admin()) as client:
        resp = await client.delete(f"/bookings/{booking.id}/guests/{guest.id}")
    assert resp.status_code == 204


async def test_non_admin_cannot_delete_guest(booking):
    guest = await _seed_guest(booking)
    async with _client(make_property_owner(user_id=PROPERTY_OWNER_ID)) as client:
        resp = await client.delete(f"/bookings/{booking.id}/guests/{guest.id}")
    assert resp.status_code == 403

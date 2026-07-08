from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.checkin_token import generate_checkin_token
from app.deps import get_booking_from_checkin_token, get_properties_client
from app.exception_handlers import sanitized_validation_error_handler
from app.limiter import limiter
from app.models import Booking
from app.routers.checkin import router

from .factories import CUSTOMER_ID, PROPERTY_ID, PROPERTY_OWNER_ID


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
        start_date=date.today() + timedelta(days=2),
        end_date=date.today() + timedelta(days=5),
        price_per_night="50.00",
        total_price="150.00",
        num_guests=2,
    )


class _MockPropertiesClient:
    async def get_property(self, property_id, user):
        return {"name": "Sea View Villa", "city": "Burgas"}


def _build_app(booking: Booking | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.limiter = limiter
    app.add_exception_handler(RequestValidationError, sanitized_validation_error_handler)

    async def _get_properties_client():
        return _MockPropertiesClient()

    app.dependency_overrides[get_properties_client] = _get_properties_client

    if booking is not None:

        async def _get_booking():
            return booking

        app.dependency_overrides[get_booking_from_checkin_token] = _get_booking

    return app


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
        pin_egn="8001010008",
    )
    return {**base, **overrides}


def _http(app: FastAPI) -> AsyncClient:
    # AsyncClient + ASGITransport runs the app in the *same* event loop as the
    # test, so it shares the fixture's in-memory SQLite connection. Starlette's
    # TestClient uses a separate loop → a different (empty) :memory: database.
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_roster_shows_open_slots_for_new_booking(booking):
    async with _http(_build_app(booking)) as client:
        resp = await client.get("/checkin/dummy-token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_slots"] == 2
    assert body["filled_slots"] == 0
    assert all(slot["filled"] is False for slot in body["roster"])


async def test_post_guest_fills_a_slot(booking):
    async with _http(_build_app(booking)) as client:
        resp = await client.post("/checkin/dummy-token/guests", json=_guest_payload())
        assert resp.status_code == 201
        assert resp.json()["filled"] is True
        assert resp.json()["first_name"] == "Ivan"
        assert "document_number" not in resp.json()
        assert "pin_egn" not in resp.json()

        roster = (await client.get("/checkin/dummy-token")).json()
    assert roster["filled_slots"] == 1


async def test_post_guest_rejects_when_roster_full(booking):
    async with _http(_build_app(booking)) as client:
        await client.post("/checkin/dummy-token/guests", json=_guest_payload())
        await client.post(
            "/checkin/dummy-token/guests",
            json=_guest_payload(
                pin_egn="9506150018",
                gender="female",
                date_of_birth="1995-06-15",
                first_name="Maria",
            ),
        )
        resp = await client.post(
            "/checkin/dummy-token/guests", json=_guest_payload(first_name="Extra")
        )
    assert resp.status_code == 409


async def test_delete_frees_the_slot(booking):
    async with _http(_build_app(booking)) as client:
        created = (
            await client.post("/checkin/dummy-token/guests", json=_guest_payload())
        ).json()
        resp = await client.delete(f"/checkin/dummy-token/guests/{created['guest_id']}")
        assert resp.status_code == 204

        roster = (await client.get("/checkin/dummy-token")).json()
    assert roster["filled_slots"] == 0


async def test_delete_missing_guest_404s(booking):
    async with _http(_build_app(booking)) as client:
        resp = await client.delete(f"/checkin/dummy-token/guests/{uuid4()}")
    assert resp.status_code == 404


async def test_validation_error_never_echoes_pin_egn_through_real_token_flow():
    booking_obj = await Booking.create(
        property_id=PROPERTY_ID,
        property_owner_id=PROPERTY_OWNER_ID,
        user_id=CUSTOMER_ID,
        start_date=date.today() + timedelta(days=2),
        end_date=date.today() + timedelta(days=5),
        price_per_night="50.00",
        total_price="150.00",
        num_guests=2,
    )
    token = generate_checkin_token(booking_obj.id, end_date=booking_obj.end_date)
    async with _http(_build_app(booking=None)) as client:
        resp = await client.post(
            f"/checkin/{token}/guests", json=_guest_payload(pin_egn="8001010035")
        )
    assert resp.status_code == 422
    assert "8001010035" not in resp.text


async def test_garbage_token_is_rejected_with_401():
    async with _http(_build_app(booking=None)) as client:
        resp = await client.get("/checkin/not-a-real-token")
    assert resp.status_code == 401

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_current_user
from app.limiter import limiter
from app.routers.booking import router
from app.schemas import BookingResponse

from .factories import CUSTOMER_ID, make_admin, make_customer, make_property_owner


def _booking_response(**overrides) -> BookingResponse:
    base = dict(
        id=str(uuid4()),
        property_id=str(uuid4()),
        property_owner_id=str(uuid4()),
        user_id=str(CUSTOMER_ID),
        start_date=(date.today() + timedelta(days=1)).isoformat(),
        end_date=(date.today() + timedelta(days=3)).isoformat(),
        status="confirmed",
        price_per_night="50.00",
        total_price="100.00",
        currency="EUR",
        num_guests=1,
        guest_name=None,
        guest_email=None,
        guest_phone=None,
        guest_country=None,
        special_requests=None,
        gap_adjustment_pct="0.00",
        updated_at=date.today().isoformat() + "T00:00:00",
    )
    return BookingResponse.model_validate({**base, **overrides})


def _client(current_user) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.limiter = limiter

    async def _user():
        return current_user

    app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=True)


def test_owner_gets_checkin_link():
    booking = _booking_response()
    with patch(
        "app.routers.booking.booking_crud.get_booking", new=AsyncMock(return_value=booking)
    ):
        resp = _client(make_customer(user_id=CUSTOMER_ID)).get(
            f"/bookings/{booking.id}/checkin-link"
        )
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_non_owner_gets_403():
    booking = _booking_response()
    with patch(
        "app.routers.booking.booking_crud.get_booking", new=AsyncMock(return_value=booking)
    ):
        resp = _client(make_property_owner()).get(f"/bookings/{booking.id}/checkin-link")
    assert resp.status_code == 403


def test_admin_can_fetch_any_bookings_link():
    booking = _booking_response()
    with patch(
        "app.routers.booking.booking_crud.get_booking", new=AsyncMock(return_value=booking)
    ):
        resp = _client(make_admin()).get(f"/bookings/{booking.id}/checkin-link")
    assert resp.status_code == 200


def test_unconfirmed_booking_returns_409():
    booking = _booking_response(status="pending")
    with patch(
        "app.routers.booking.booking_crud.get_booking", new=AsyncMock(return_value=booking)
    ):
        resp = _client(make_customer(user_id=CUSTOMER_ID)).get(
            f"/bookings/{booking.id}/checkin-link"
        )
    assert resp.status_code == 409


def test_expired_link_returns_410():
    booking = _booking_response(
        start_date=(date.today() - timedelta(days=32)).isoformat(),
        end_date=(date.today() - timedelta(days=30)).isoformat(),
    )
    with patch(
        "app.routers.booking.booking_crud.get_booking", new=AsyncMock(return_value=booking)
    ):
        resp = _client(make_customer(user_id=CUSTOMER_ID)).get(
            f"/bookings/{booking.id}/checkin-link"
        )
    assert resp.status_code == 410

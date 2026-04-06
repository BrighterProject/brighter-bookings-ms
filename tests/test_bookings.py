"""
Full endpoint test suite for /bookings.

Testing strategy:
  - Auth/scope deps are overridden via conftest.build_app()
  - CRUD methods are patched per-test with AsyncMock (no DB)
  - PropertiesClient is injected as a mock via client_factory(..., properties_client=mock_vc)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.deps import get_current_user
from app.schemas import BookingResponse, BookingSlot
from app.scopes import BookingScope

from .factories import (
    BOOKING_ID,
    CUSTOMER_ID,
    PROPERTY_ID,
    PROPERTY_OWNER_ID,
    booking_create_payload,
    booking_response,
    make_customer,
    make_property_owner,
    user_dict,
    property_dict,
)


def booking_model(**overrides) -> BookingResponse:
    """BookingResponse Pydantic object — needed when router accesses .status etc."""
    return BookingResponse(**booking_response(**overrides))


CRUD_PATH = "app.routers.booking.booking_crud"


# ---------------------------------------------------------------------------
# GET /bookings
# ---------------------------------------------------------------------------


class TestListBookings:
    def test_customer_sees_own_bookings(self, customer_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
            resp = customer_client.get("/bookings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(BOOKING_ID)

    def test_admin_sees_all_bookings(self, admin_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
            resp = admin_client.get("/bookings")
        assert resp.status_code == 200
        # Admin path: no user_id or property_owner_id filter
        _, kwargs = mock_crud.list_bookings.call_args
        assert kwargs.get("user_id") is None
        assert kwargs.get("property_owner_id") is None

    def test_property_owner_sees_property_bookings(self, owner_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
            resp = owner_client.get("/bookings")
        assert resp.status_code == 200
        _, kwargs = mock_crud.list_bookings.call_args
        assert kwargs.get("property_owner_id") == PROPERTY_OWNER_ID

    def test_customer_user_id_filter_applied(self, client_factory):
        client = client_factory(make_customer())
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[])
            resp = client.get("/bookings")
        assert resp.status_code == 200
        _, kwargs = mock_crud.list_bookings.call_args
        assert kwargs.get("user_id") == CUSTOMER_ID

    def test_status_filter_forwarded(self, customer_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[])
            resp = customer_client.get("/bookings", params={"status": "confirmed"})
        assert resp.status_code == 200
        _, kwargs = mock_crud.list_bookings.call_args
        assert kwargs["filters"].status == "confirmed"

    def test_missing_auth_headers_returns_422(self, anon_app):
        with TestClient(anon_app) as c:
            resp = c.get("/bookings")
        assert resp.status_code == 422

    def test_no_relevant_scope_returns_403(self, anon_app):
        async def _no_scope_user():
            return make_customer(scopes=["properties:read"])  # no bookings scope at all

        anon_app.dependency_overrides[get_current_user] = _no_scope_user
        with TestClient(anon_app) as c:
            resp = c.get("/bookings")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /bookings
# ---------------------------------------------------------------------------


class TestCreateBooking:
    def _mock_vc(self, property_status: str = "active") -> MagicMock:
        mock_vc = MagicMock()
        mock_vc.get_property = AsyncMock(return_value=property_dict(status=property_status))
        mock_vc.get_unavailabilities = AsyncMock(return_value=[])
        return mock_vc

    def test_success_returns_201(self, client_factory):
        client = client_factory(make_customer(), properties_client=self._mock_vc())
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.create_booking = AsyncMock(return_value=booking_response())
            resp = client.post("/bookings", json=booking_create_payload())
        assert resp.status_code == 201
        assert resp.json()["id"] == str(BOOKING_ID)

    def test_property_id_forwarded_to_properties_client(self, client_factory):
        mock_vc = self._mock_vc()
        client = client_factory(make_customer(), properties_client=mock_vc)
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.create_booking = AsyncMock(return_value=booking_response())
            client.post("/bookings", json=booking_create_payload())
        mock_vc.get_property.assert_awaited_once()
        called_property_id = mock_vc.get_property.call_args[0][0]
        assert str(called_property_id) == str(PROPERTY_ID)

    def test_property_not_found_returns_404(self, client_factory):
        mock_vc = MagicMock()
        mock_vc.get_property = AsyncMock(return_value=None)
        client = client_factory(make_customer(), properties_client=mock_vc)
        resp = client.post("/bookings", json=booking_create_payload())
        assert resp.status_code == 404
        assert "Property not found" in resp.json()["detail"]

    def test_property_not_active_returns_422(self, client_factory):
        client = client_factory(
            make_customer(), properties_client=self._mock_vc(property_status="inactive")
        )
        resp = client.post("/bookings", json=booking_create_payload())
        assert resp.status_code == 422
        assert "not available" in resp.json()["detail"]

    def test_invalid_payload_returns_422(self, client_factory):
        client = client_factory(make_customer(), properties_client=self._mock_vc())
        resp = client.post("/bookings", json={"property_id": str(PROPERTY_ID)})
        assert resp.status_code == 422

    def test_end_before_start_returns_422(self, client_factory):
        from .factories import LATER, NOW

        client = client_factory(make_customer(), properties_client=self._mock_vc())
        payload = booking_create_payload(
            start_datetime=LATER.isoformat(), end_datetime=NOW.isoformat()
        )
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 422

    def test_duration_too_short_returns_422(self, client_factory):
        from datetime import timedelta

        from .factories import NOW

        client = client_factory(make_customer(), properties_client=self._mock_vc())
        payload = booking_create_payload(
            start_datetime=NOW.isoformat(),
            end_datetime=(NOW + timedelta(minutes=30)).isoformat(),
        )
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 422

    def test_missing_write_scope_returns_403(self, anon_app):
        async def _read_only():
            return make_customer(scopes=[BookingScope.READ])

        anon_app.dependency_overrides[get_current_user] = _read_only
        with TestClient(anon_app) as c:
            resp = c.post("/bookings", json=booking_create_payload())
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /bookings/{id}
# ---------------------------------------------------------------------------


class TestGetBooking:
    def test_customer_gets_own_booking(self, customer_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=booking_response())
            resp = customer_client.get(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(BOOKING_ID)

    def test_customer_cannot_see_others_booking_returns_404(self, customer_client):
        # CRUD returns None because user_id doesn't match
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=None)
            resp = customer_client.get(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 404

    def test_admin_can_see_any_booking(self, admin_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=booking_response())
            resp = admin_client.get(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 200
        # Admin path: no user_id or property_owner_id filter
        _, kwargs = mock_crud.get_booking.call_args
        assert kwargs.get("user_id") is None
        assert kwargs.get("property_owner_id") is None

    def test_property_owner_gets_booking_for_their_property(self, owner_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=booking_response())
            resp = owner_client.get(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 200
        _, kwargs = mock_crud.get_booking.call_args
        assert kwargs.get("property_owner_id") == PROPERTY_OWNER_ID

    def test_not_found_returns_404(self, customer_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=None)
            resp = customer_client.get(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /bookings/{id}/status
# ---------------------------------------------------------------------------


class TestUpdateBookingStatus:
    """
    Status transitions use get_current_user directly — no pre-built dep override.
    The mock for get_booking must return a BookingResponse Pydantic object
    because the router accesses .status, .user_id, .property_owner_id attributes.
    """

    def test_property_owner_confirms_pending_booking(self, client_factory):
        client = client_factory(make_property_owner())
        pending = booking_model(status="pending", property_owner_id=str(PROPERTY_OWNER_ID))
        confirmed = booking_response(status="confirmed")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            mock_crud.update_booking_status = AsyncMock(return_value=confirmed)
            resp = client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "confirmed"}
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_admin_confirms_booking(self, admin_client):
        pending = booking_model(status="pending")
        confirmed = booking_response(status="confirmed")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            mock_crud.update_booking_status = AsyncMock(return_value=confirmed)
            resp = admin_client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "confirmed"}
            )
        assert resp.status_code == 200

    def test_customer_cannot_confirm_returns_403(self, client_factory):
        client = client_factory(make_customer())
        pending = booking_model(
            status="pending",
            property_owner_id=str(PROPERTY_OWNER_ID),
            user_id=str(CUSTOMER_ID),
        )
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            resp = client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "confirmed"}
            )
        assert resp.status_code == 403

    def test_customer_cancels_own_booking(self, client_factory):
        client = client_factory(make_customer())
        pending = booking_model(
            status="pending",
            user_id=str(CUSTOMER_ID),
            property_owner_id=str(PROPERTY_OWNER_ID),
        )
        cancelled = booking_response(status="cancelled")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            mock_crud.update_booking_status = AsyncMock(return_value=cancelled)
            resp = client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "cancelled"}
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_admin_cancels_booking(self, admin_client):
        pending = booking_model(status="pending")
        cancelled = booking_response(status="cancelled")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            mock_crud.update_booking_status = AsyncMock(return_value=cancelled)
            resp = admin_client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "cancelled"}
            )
        assert resp.status_code == 200

    def test_property_owner_can_refuse_pending_booking(self, client_factory):
        """Property owner can cancel (refuse) a pending booking for their own property."""
        from uuid import uuid4

        client = client_factory(make_property_owner())
        pending = booking_model(
            status="pending",
            user_id=str(uuid4()),
            property_owner_id=str(PROPERTY_OWNER_ID),
        )
        cancelled = booking_response(status="cancelled")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            mock_crud.update_booking_status = AsyncMock(return_value=cancelled)
            resp = client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "cancelled"}
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_property_owner_cannot_cancel_other_properties_booking_returns_403(
        self, client_factory
    ):
        """Property owner cannot cancel a booking belonging to a different property."""
        from uuid import uuid4

        client = client_factory(make_property_owner())
        pending = booking_model(
            status="pending",
            user_id=str(uuid4()),
            property_owner_id=str(uuid4()),  # different owner
        )
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            resp = client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "cancelled"}
            )
        assert resp.status_code == 403

    def test_property_owner_completes_confirmed_booking(self, client_factory):
        client = client_factory(make_property_owner())
        confirmed = booking_model(
            status="confirmed", property_owner_id=str(PROPERTY_OWNER_ID)
        )
        completed = booking_response(status="completed")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=confirmed)
            mock_crud.update_booking_status = AsyncMock(return_value=completed)
            resp = client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "completed"}
            )
        assert resp.status_code == 200

    def test_property_owner_marks_no_show(self, client_factory):
        client = client_factory(make_property_owner())
        confirmed = booking_model(
            status="confirmed", property_owner_id=str(PROPERTY_OWNER_ID)
        )
        no_show = booking_response(status="no_show")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=confirmed)
            mock_crud.update_booking_status = AsyncMock(return_value=no_show)
            resp = client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "no_show"}
            )
        assert resp.status_code == 200

    def test_invalid_transition_from_cancelled_returns_400(self, admin_client):
        cancelled = booking_model(status="cancelled")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=cancelled)
            resp = admin_client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "confirmed"}
            )
        assert resp.status_code == 400

    def test_invalid_transition_from_completed_returns_400(self, admin_client):
        completed = booking_model(status="completed")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=completed)
            resp = admin_client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "confirmed"}
            )
        assert resp.status_code == 400

    def test_booking_not_found_returns_404(self, admin_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=None)
            resp = admin_client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "confirmed"}
            )
        assert resp.status_code == 404

    def test_update_crud_returns_none_gives_404(self, admin_client):
        """Edge case: booking disappears between get and update (race condition)."""
        pending = booking_model(status="pending")
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=pending)
            mock_crud.update_booking_status = AsyncMock(return_value=None)
            resp = admin_client.patch(
                f"/bookings/{BOOKING_ID}/status", json={"status": "confirmed"}
            )
        assert resp.status_code == 404

    def test_invalid_status_value_returns_422(self, admin_client):
        resp = admin_client.patch(
            f"/bookings/{BOOKING_ID}/status", json={"status": "flying"}
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Enrichment — property_name / customer_username / owner_username
# ---------------------------------------------------------------------------


class TestEnrichment:
    def _mock_vc(self, properties: list[dict] | None = None):
        mock = MagicMock()
        mock.get_by_ids = AsyncMock(return_value=properties or [])
        mock.get_property = AsyncMock(return_value=None)
        mock.get_unavailabilities = AsyncMock(return_value=[])
        return mock

    def _mock_uc(self, users: list[dict] | None = None):
        mock = MagicMock()
        mock.get_by_ids = AsyncMock(return_value=users or [])
        return mock

    def test_list_returns_property_name(self, client_factory):
        vc = self._mock_vc([property_dict(name="My Court")])
        uc = self._mock_uc()
        client = client_factory(make_customer(), properties_client=vc, users_client=uc)
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
            resp = client.get("/bookings")
        assert resp.status_code == 200
        assert resp.json()[0]["property_name"] == "My Court"

    def test_list_returns_customer_username(self, client_factory):
        vc = self._mock_vc()
        uc = self._mock_uc(
            [user_dict(user_id=CUSTOMER_ID, username="johndoe", full_name="John Doe")]
        )
        client = client_factory(make_customer(), properties_client=vc, users_client=uc)
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
            resp = client.get("/bookings")
        data = resp.json()[0]
        assert data["customer_username"] == "johndoe"
        assert data["customer_full_name"] == "John Doe"

    def test_list_returns_owner_username(self, client_factory):
        vc = self._mock_vc()
        uc = self._mock_uc(
            [user_dict(user_id=PROPERTY_OWNER_ID, username="owner42")]
        )
        client = client_factory(make_customer(), properties_client=vc, users_client=uc)
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
            resp = client.get("/bookings")
        assert resp.json()[0]["owner_username"] == "owner42"

    def test_enrichment_fields_null_when_upstream_empty(self, client_factory):
        client = client_factory(make_customer())  # uses noop mocks → empty lists
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_bookings = AsyncMock(return_value=[booking_response()])
            resp = client.get("/bookings")
        data = resp.json()[0]
        assert data["property_name"] is None
        assert data["customer_username"] is None
        assert data["owner_username"] is None

    def test_get_booking_returns_enriched(self, client_factory):
        vc = self._mock_vc([property_dict(name="Stadium A")])
        uc = self._mock_uc([user_dict(user_id=CUSTOMER_ID, username="alice")])
        client = client_factory(make_customer(), properties_client=vc, users_client=uc)
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.get_booking = AsyncMock(return_value=booking_response())
            resp = client.get(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["property_name"] == "Stadium A"
        assert data["customer_username"] == "alice"


# ---------------------------------------------------------------------------
# DELETE /bookings/{id}
# ---------------------------------------------------------------------------


class TestDeleteBooking:
    def test_admin_can_delete(self, admin_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.delete_booking = AsyncMock(return_value=True)
            resp = admin_client.delete(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 204
        mock_crud.delete_booking.assert_awaited_once_with(BOOKING_ID)

    def test_admin_delete_not_found_returns_404(self, admin_client):
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.delete_booking = AsyncMock(return_value=False)
            resp = admin_client.delete(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 404

    def test_non_admin_gets_403(self, anon_app):
        async def _customer():
            return make_customer()

        anon_app.dependency_overrides[get_current_user] = _customer
        with TestClient(anon_app) as c:
            resp = c.delete(f"/bookings/{BOOKING_ID}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /bookings/slots  (public — no auth required)
# ---------------------------------------------------------------------------


SLOT = BookingSlot(
    start_datetime="2026-05-01T12:00:00",
    end_datetime="2026-05-07T10:00:00",
)


class TestGetSlots:
    def test_returns_slots_unauthenticated(self, anon_app):
        with patch("app.routers.booking.get_slots_cache", return_value=None), \
             patch("app.routers.booking.set_slots_cache"), \
             patch(CRUD_PATH) as mock_crud:
            mock_crud.list_occupied_slots = AsyncMock(return_value=[SLOT])
            with TestClient(anon_app) as c:
                resp = c.get(f"/bookings/slots?property_id={PROPERTY_ID}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_returns_empty_list_when_no_bookings(self, anon_app):
        with patch("app.routers.booking.get_slots_cache", return_value=None), \
             patch("app.routers.booking.set_slots_cache"), \
             patch(CRUD_PATH) as mock_crud:
            mock_crud.list_occupied_slots = AsyncMock(return_value=[])
            with TestClient(anon_app) as c:
                resp = c.get(f"/bookings/slots?property_id={PROPERTY_ID}")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_serves_from_cache(self, anon_app):
        cached = [SLOT.model_dump(mode="json")]
        with patch("app.routers.booking.get_slots_cache", return_value=cached):
            with TestClient(anon_app) as c:
                resp = c.get(f"/bookings/slots?property_id={PROPERTY_ID}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_missing_property_id_returns_422(self, anon_app):
        with TestClient(anon_app) as c:
            resp = c.get("/bookings/slots")
        assert resp.status_code == 422

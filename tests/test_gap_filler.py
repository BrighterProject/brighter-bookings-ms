"""Tests for Smart Gap Filler validation in create_booking endpoint."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas import BookingSlot

from .factories import (
    BOOKING_ID,
    PROPERTY_ID,
    PROPERTY_OWNER_ID,
    booking_create_payload,
    booking_response,
    make_customer,
    property_dict,
)

CRUD_PATH = "app.routers.booking.booking_crud"


def _mock_vc(prop: dict | None = None) -> MagicMock:
    """Build a PropertiesClient mock returning `prop` for get_property."""
    mock_vc = MagicMock()
    mock_vc.get_property = AsyncMock(return_value=prop)
    mock_vc.get_unavailabilities = AsyncMock(return_value=[])
    mock_vc.get_by_ids = AsyncMock(return_value=[])
    return mock_vc


def _mock_pricing(total: str = "100.00", per_night: str = "50.00") -> MagicMock:
    mock = MagicMock()
    mock.resolve = AsyncMock(return_value=(Decimal(total), Decimal(per_night)))
    return mock


class TestGapFillerValidation:
    def test_normal_booking_meets_min_nights_succeeds(self, client_factory):
        """Booking >= min_nights passes without gap filler check."""
        prop = property_dict(min_nights=2, enable_gap_filler=False)
        # 2-night stay meets min_nights=2
        today = date.today()
        start = today + timedelta(days=30)
        end = start + timedelta(days=2)
        payload = booking_create_payload(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        client = client_factory(
            make_customer(),
            properties_client=_mock_vc(prop),
            pricing_client=_mock_pricing("100.00", "50.00"),
        )
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.create_booking = AsyncMock(return_value=booking_response(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            ))
            resp = client.post("/bookings", json=payload)
        assert resp.status_code == 201

    def test_short_booking_gap_filler_disabled_returns_400(self, client_factory):
        """Booking < min_nights with gap filler disabled → 400."""
        prop = property_dict(min_nights=3, enable_gap_filler=False)
        today = date.today()
        start = today + timedelta(days=30)
        end = start + timedelta(days=1)  # 1 night < min_nights=3
        payload = booking_create_payload(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        client = client_factory(
            make_customer(),
            properties_client=_mock_vc(prop),
        )
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 400
        assert "minimum night requirement" in resp.json()["detail"]

    def test_short_booking_gap_filler_enabled_outside_window_returns_400(
        self, client_factory
    ):
        """Gap filler enabled but check-in is beyond last-minute window → 400."""
        prop = property_dict(
            min_nights=3,
            enable_gap_filler=True,
            gap_last_minute_window=7,
            gap_adjacent_only=False,
        )
        today = date.today()
        start = today + timedelta(days=20)  # 20 days out > 7-day window
        end = start + timedelta(days=1)
        payload = booking_create_payload(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        client = client_factory(
            make_customer(),
            properties_client=_mock_vc(prop),
        )
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == 400
        assert "minimum night requirement" in resp.json()["detail"]

    def test_short_booking_gap_filler_within_window_adjacent_succeeds_with_premium(
        self, client_factory
    ):
        """Gap filler enabled, within window, adjacent bookings exist → 201 with gap premium."""
        today = date.today()
        start = today + timedelta(days=3)  # within 7-day window
        end = start + timedelta(days=1)    # 1-night stay

        prop = property_dict(
            min_nights=3,
            enable_gap_filler=True,
            gap_premium_pct="20.00",
            gap_last_minute_window=7,
            gap_adjacent_only=True,
        )

        # Adjacent slots: one booking ends on start, another starts on end
        adjacent_slots = [
            BookingSlot(start_date=start - timedelta(days=2), end_date=start),
            BookingSlot(start_date=end, end_date=end + timedelta(days=3)),
        ]

        # Pricing returns 50/night base; gap premium (20%) applied in router
        client = client_factory(
            make_customer(),
            properties_client=_mock_vc(prop),
            pricing_client=_mock_pricing("50.00", "50.00"),
        )
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_occupied_slots = AsyncMock(return_value=adjacent_slots)
            mock_crud.create_booking = AsyncMock(return_value=booking_response(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                gap_adjustment_pct="20.00",
                total_price="60.00",
            ))
            resp = client.post("/bookings", json=booking_create_payload(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            ))

        assert resp.status_code == 201
        data = resp.json()
        assert float(data["gap_adjustment_pct"]) == 20.0

        # Verify create_booking was called with applied gap pct
        _, kwargs = mock_crud.create_booking.call_args
        assert kwargs["gap_adjustment_pct"] == Decimal("20.00")

    def test_short_booking_gap_adjacent_only_false_within_window_succeeds(
        self, client_factory
    ):
        """Gap filler enabled, gap_adjacent_only=False, within window → 201 without adjacency check."""
        today = date.today()
        start = today + timedelta(days=1)
        end = start + timedelta(days=2)  # 2-night stay, min_nights=3

        prop = property_dict(
            min_nights=3,
            enable_gap_filler=True,
            gap_premium_pct="0.00",
            gap_last_minute_window=30,
            gap_adjacent_only=False,
        )

        client = client_factory(
            make_customer(),
            properties_client=_mock_vc(prop),
            pricing_client=_mock_pricing("100.00", "50.00"),
        )
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.create_booking = AsyncMock(return_value=booking_response(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            ))
            resp = client.post("/bookings", json=booking_create_payload(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            ))
        assert resp.status_code == 201

    def test_short_booking_gap_filler_adjacent_only_no_adjacent_bookings_returns_400(
        self, client_factory
    ):
        """Gap filler enabled, within window, but no adjacent bookings → 400."""
        today = date.today()
        start = today + timedelta(days=3)
        end = start + timedelta(days=1)

        prop = property_dict(
            min_nights=3,
            enable_gap_filler=True,
            gap_premium_pct="0.00",
            gap_last_minute_window=7,
            gap_adjacent_only=True,
        )

        client = client_factory(
            make_customer(),
            properties_client=_mock_vc(prop),
        )
        with patch(CRUD_PATH) as mock_crud:
            mock_crud.list_occupied_slots = AsyncMock(return_value=[])
            resp = client.post("/bookings", json=booking_create_payload(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            ))
        assert resp.status_code == 400
        assert "minimum night requirement" in resp.json()["detail"]

"""Unit tests for the status-change notification payload builder.

Exercises `_notify_booking_status_changed` directly (it is normally fired as a
background task) to assert that cancellation emails carry a substituted
`refund_amount` and locale-formatted dates.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.routers.booking import _notify_booking_status_changed
from app.schemas import BookingStatus

from .factories import user_dict


def _booking():
    return MagicMock(
        id="booking-1",
        property_id="property-1",
        user_id="user-1",
        guest_email=None,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        total_price="100.00",
        currency="EUR",
    )


def _run_cancel(*, guest_locale: str, refund_amount: float):
    booking = _booking()
    users_client = MagicMock()
    users_client.get_by_ids = AsyncMock(
        return_value=[user_dict(email="guest@example.com", locale=guest_locale)]
    )
    properties_client = MagicMock()
    properties_client.get_property = AsyncMock(return_value=None)
    nc = MagicMock()
    nc.send = AsyncMock()

    asyncio.run(
        _notify_booking_status_changed(
            booking,
            BookingStatus.CANCELLED,
            users_client,
            nc,
            properties_client,
            refund_amount=refund_amount,
        )
    )
    nc.send.assert_awaited_once()
    return nc.send.await_args.kwargs


class TestCancellationNotification:
    def test_refund_amount_is_substituted(self):
        kwargs = _run_cancel(guest_locale="en", refund_amount=75.0)
        assert kwargs["data"]["refund_amount"] == "75.00"

    def test_no_refund_renders_zero_not_placeholder(self):
        kwargs = _run_cancel(guest_locale="en", refund_amount=0.0)
        assert kwargs["data"]["refund_amount"] == "0.00"

    def test_dates_localized_to_bulgarian(self):
        kwargs = _run_cancel(guest_locale="bg", refund_amount=100.0)
        data = kwargs["data"]
        assert "юни" in data["start_date"]
        assert "юни" in data["end_date"]
        # cancelled_date is date.today(); assert against the current Bulgarian
        # month so the test is not pinned to the month it was written in.
        bg_months = [
            "",
            "януари", "февруари", "март", "април", "май", "юни",
            "юли", "август", "септември", "октомври", "ноември", "декември",
        ]
        assert bg_months[date.today().month] in data["cancelled_date"]
        assert kwargs["locale"] == "bg"

    def test_dates_english_by_default(self):
        kwargs = _run_cancel(guest_locale="en", refund_amount=100.0)
        assert "June" in kwargs["data"]["start_date"]

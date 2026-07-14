"""Sync-engine tests (BTR-41): the pure diff, the orchestrator, and SSRF fetch."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.models import BookingChannel
from app.schemas import BookingResponse, FeedSyncStatus
from app.services.calendar_sync import (
    FeedFetchError,
    diff_feed,
    fetch_ics,
    sync_all_active_feeds,
    sync_feed,
)
from app.services.ical_parser import ParsedEvent

from .factories import booking_response

SYNC = "app.services.calendar_sync"
TODAY = date(2026, 7, 12)


def _existing(
    uid: str, start: date, end: date, status: str = "confirmed", bid=None
) -> BookingResponse:
    return BookingResponse(
        **booking_response(
            id=str(bid or uuid4()),
            channel="booking_com",
            external_uid=uid,
            status=status,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
    )


def _event(uid: str, start: date, end: date) -> ParsedEvent:
    return ParsedEvent(uid=uid, start_date=start, end_date=end)


# ---------------------------------------------------------------------------
# diff_feed — pure reconciliation logic
# ---------------------------------------------------------------------------


class TestDiffFeed:
    def test_new_uid_creates(self):
        actions = diff_feed([], [_event("u1", date(2026, 8, 1), date(2026, 8, 4))], TODAY)
        assert len(actions.creates) == 1
        assert not actions.updates and not actions.cancels and not actions.truncations

    def test_changed_dates_updates(self):
        bid = uuid4()
        existing = [_existing("u1", date(2026, 8, 1), date(2026, 8, 4), bid=bid)]
        incoming = [_event("u1", date(2026, 8, 1), date(2026, 8, 6))]  # extended
        actions = diff_feed(existing, incoming, TODAY)
        assert actions.updates == [(bid, date(2026, 8, 1), date(2026, 8, 6))]
        assert not actions.creates

    def test_identical_confirmed_is_noop(self):
        existing = [_existing("u1", date(2026, 8, 1), date(2026, 8, 4))]
        incoming = [_event("u1", date(2026, 8, 1), date(2026, 8, 4))]
        actions = diff_feed(existing, incoming, TODAY)
        assert not (actions.creates or actions.updates or actions.cancels or actions.truncations)

    def test_reappearing_cancelled_uid_is_resurrected(self):
        bid = uuid4()
        existing = [
            _existing("u1", date(2026, 8, 1), date(2026, 8, 4), status="cancelled", bid=bid)
        ]
        incoming = [_event("u1", date(2026, 8, 1), date(2026, 8, 4))]
        actions = diff_feed(existing, incoming, TODAY)
        # Present in feed but not CONFIRMED → re-confirm via a date update.
        assert actions.updates == [(bid, date(2026, 8, 1), date(2026, 8, 4))]

    def test_vanished_future_booking_is_cancelled(self):
        bid = uuid4()
        existing = [
            _existing("u1", date(2026, 8, 1), date(2026, 8, 4), bid=bid)
        ]  # starts after today
        actions = diff_feed(existing, [], TODAY)
        assert actions.cancels == [bid]
        assert not actions.truncations

    def test_vanished_midstay_is_truncated_to_today(self):
        bid = uuid4()
        # start < today <= end → guest left early / stay shortened
        existing = [_existing("u1", date(2026, 7, 10), date(2026, 7, 15), bid=bid)]
        actions = diff_feed(existing, [], TODAY)
        assert actions.truncations == [(bid, TODAY)]
        assert not actions.cancels

    def test_vanished_fully_elapsed_is_left_untouched(self):
        # end_date < today → aged out ("the vanishing past"), never cancel
        existing = [_existing("u1", date(2026, 7, 1), date(2026, 7, 5))]
        actions = diff_feed(existing, [], TODAY)
        assert not (actions.cancels or actions.truncations or actions.updates)

    def test_vanished_already_cancelled_is_left_untouched(self):
        existing = [_existing("u1", date(2026, 8, 1), date(2026, 8, 4), status="cancelled")]
        actions = diff_feed(existing, [], TODAY)
        assert not (actions.cancels or actions.truncations)

    def test_checkout_today_boundary_left_untouched(self):
        # start < today, end == today → last night already elapsed; no write
        existing = [_existing("u1", date(2026, 7, 10), TODAY)]
        actions = diff_feed(existing, [], TODAY)
        assert not (actions.cancels or actions.truncations)


# ---------------------------------------------------------------------------
# fetch_ics — SSRF-revalidated redirect handling
# ---------------------------------------------------------------------------


def _client_factory(handler):
    """Return a drop-in for httpx.AsyncClient backed by a MockTransport.

    Captures the real class so the patched name never recurses.
    """
    real_cls = httpx.AsyncClient

    def make(**kwargs):
        kwargs.pop("transport", None)
        return real_cls(transport=httpx.MockTransport(handler), **kwargs)

    return make


BC = BookingChannel.BOOKING_COM


class TestFetchIcs:
    async def test_follows_booking_com_redirect(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/a.ics":
                return httpx.Response(302, headers={"location": "https://cdn.booking.com/b.ics"})
            return httpx.Response(200, text="BEGIN:VCALENDAR\nEND:VCALENDAR\n")

        with (
            patch(f"{SYNC}.assert_host_is_public"),
            patch("httpx.AsyncClient", _client_factory(handler)),
        ):
            body = await fetch_ics("https://admin.booking.com/a.ics", timeout=5, channel=BC)
        assert "VCALENDAR" in body

    async def test_follows_airbnb_redirect(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "www.airbnb.com":
                return httpx.Response(302, headers={"location": "https://cdn.airbnb.com/b.ics"})
            return httpx.Response(200, text="BEGIN:VCALENDAR\nEND:VCALENDAR\n")

        with (
            patch(f"{SYNC}.assert_host_is_public"),
            patch("httpx.AsyncClient", _client_factory(handler)),
        ):
            body = await fetch_ics(
                "https://www.airbnb.com/calendar/ical/1.ics",
                timeout=5,
                channel=BookingChannel.AIRBNB,
            )
        assert "VCALENDAR" in body

    async def test_redirect_to_non_allowlisted_host_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://evil.com/x.ics"})

        # Redirect target fails the per-hop host allowlist → FeedUrlError, not retried.
        with (
            patch(f"{SYNC}.assert_host_is_public"),
            patch("httpx.AsyncClient", _client_factory(handler)),
            pytest.raises(Exception) as exc,
        ):
            await fetch_ics("https://admin.booking.com/a.ics", timeout=5, channel=BC)
        assert "not allowed" in str(exc.value)

    async def test_cyclic_redirect_detected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            other = "b.ics" if request.url.path == "/a.ics" else "a.ics"
            return httpx.Response(302, headers={"location": f"https://admin.booking.com/{other}"})

        with (
            patch(f"{SYNC}.assert_host_is_public"),
            patch("httpx.AsyncClient", _client_factory(handler)),
            pytest.raises(FeedFetchError) as exc,
        ):
            await fetch_ics("https://admin.booking.com/a.ics", timeout=5, channel=BC)
        assert "Cyclic redirect" in str(exc.value)

    async def test_oversize_body_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="X" * 5000)

        with (
            patch(f"{SYNC}.assert_host_is_public"),
            patch(f"{SYNC}.settings.calendar_sync_max_bytes", 1000),
            patch("httpx.AsyncClient", _client_factory(handler)),
            pytest.raises(FeedFetchError) as exc,
        ):
            await fetch_ics("https://admin.booking.com/a.ics", timeout=5, channel=BC)
        assert "exceeds" in str(exc.value)


# ---------------------------------------------------------------------------
# sync_feed — orchestrator (all deps mocked)
# ---------------------------------------------------------------------------


def _feed_ref(content_hash=None):
    return SimpleNamespace(
        id=uuid4(),
        property_id=uuid4(),
        channel=BookingChannel.BOOKING_COM,
        url="https://admin.booking.com/ical.html?t=x",
        content_hash=content_hash,
    )


def _patched_orchestrator(*, events, feed_crud, booking_crud, property_data, hash_value):
    """Context managers patching every sync_feed dependency."""
    props = MagicMock()
    props.get_property = AsyncMock(return_value=property_data)
    return [
        patch(f"{SYNC}.fetch_ics", new=AsyncMock(return_value="ICSBODY")),
        patch(f"{SYNC}.parse_ics", return_value=events),
        patch(f"{SYNC}.compute_content_hash", return_value=hash_value),
        patch(f"{SYNC}.calendar_feed_crud", new=feed_crud),
        patch(f"{SYNC}.booking_crud", new=booking_crud),
        patch(f"{SYNC}.get_properties_client", return_value=props),
        patch(f"{SYNC}.today_in_sofia", return_value=TODAY),
        patch("app.cache.invalidate_slots_cache", new=AsyncMock()),
    ]


def _apply(ctxs):
    from contextlib import ExitStack

    stack = ExitStack()
    for c in ctxs:
        stack.enter_context(c)
    return stack


def _channel_booking_crud(existing, ranges=None):
    """MagicMock booking_crud with every channel method (bulk) wired as AsyncMock."""
    bc = MagicMock()
    bc.list_channel_bookings = AsyncMock(return_value=existing)
    bc.active_platform_ranges = AsyncMock(return_value=ranges or [])
    bc.bulk_upsert_channel_bookings = AsyncMock()
    bc.bulk_set_channel_booking_dates = AsyncMock()
    bc.bulk_cancel_channel_bookings = AsyncMock()
    bc.bulk_truncate_channel_bookings = AsyncMock()
    return bc


class TestSyncFeedOrchestrator:
    async def test_fetch_error_keeps_rows(self):
        feed_crud = MagicMock()
        feed_crud.record_sync = AsyncMock()
        booking_crud = MagicMock()
        booking_crud.list_channel_bookings = AsyncMock()
        with (
            patch(f"{SYNC}.fetch_ics", new=AsyncMock(side_effect=FeedFetchError("boom"))),
            patch(f"{SYNC}.calendar_feed_crud", new=feed_crud),
            patch(f"{SYNC}.booking_crud", new=booking_crud),
        ):
            status = await sync_feed(_feed_ref())
        assert status == FeedSyncStatus.FETCH_ERROR
        # Fail-safe: never touched existing bookings.
        booking_crud.list_channel_bookings.assert_not_called()
        assert feed_crud.record_sync.await_args.kwargs["status"] == FeedSyncStatus.FETCH_ERROR

    async def test_unchanged_hash_short_circuits(self):
        feed = _feed_ref(content_hash="SAME")
        feed_crud = MagicMock()
        feed_crud.record_sync = AsyncMock()
        booking_crud = MagicMock()
        booking_crud.list_channel_bookings = AsyncMock()
        props = MagicMock()
        props.get_property = AsyncMock()
        with (
            patch(f"{SYNC}.fetch_ics", new=AsyncMock(return_value="B")),
            patch(f"{SYNC}.parse_ics", return_value=[]),
            patch(f"{SYNC}.compute_content_hash", return_value="SAME"),
            patch(f"{SYNC}.calendar_feed_crud", new=feed_crud),
            patch(f"{SYNC}.booking_crud", new=booking_crud),
            patch(f"{SYNC}.get_properties_client", return_value=props),
        ):
            status = await sync_feed(feed)
        assert status == FeedSyncStatus.OK
        props.get_property.assert_not_called()  # short-circuited before owner resolve
        booking_crud.list_channel_bookings.assert_not_called()

    async def test_create_path_imports_booking(self):
        feed = _feed_ref(content_hash="OLD")
        owner_id = uuid4()
        events = [_event("u1", date(2026, 8, 1), date(2026, 8, 4))]
        feed_crud = MagicMock()
        feed_crud.record_sync = AsyncMock()
        booking_crud = _channel_booking_crud(existing=[], ranges=[])
        property_data = {"owner_id": str(owner_id), "currency": "EUR"}
        stack = _apply(
            _patched_orchestrator(
                events=events,
                feed_crud=feed_crud,
                booking_crud=booking_crud,
                property_data=property_data,
                hash_value="NEW",
            )
        )
        with stack:
            status = await sync_feed(feed)
        assert status == FeedSyncStatus.OK
        booking_crud.bulk_upsert_channel_bookings.assert_awaited_once()
        assert booking_crud.bulk_upsert_channel_bookings.await_args.kwargs["events"] == events
        assert feed_crud.record_sync.await_args.kwargs["content_hash"] == "NEW"

    async def test_overbooking_recorded_and_warned(self):
        feed = _feed_ref(content_hash="OLD")
        events = [_event("u1", date(2026, 8, 1), date(2026, 8, 4))]
        feed_crud = MagicMock()
        feed_crud.record_sync = AsyncMock()
        # Existing platform booking overlapping the incoming reservation.
        booking_crud = _channel_booking_crud(
            existing=[], ranges=[(date(2026, 8, 2), date(2026, 8, 3))]
        )
        stack = _apply(
            _patched_orchestrator(
                events=events,
                feed_crud=feed_crud,
                booking_crud=booking_crud,
                property_data={"owner_id": str(uuid4()), "currency": "EUR"},
                hash_value="NEW",
            )
        )
        overbookings = MagicMock()
        with stack, patch(f"{SYNC}._overbookings", overbookings):
            status = await sync_feed(feed)
        # Overbooking still recorded (reflects reality), not dropped.
        assert status == FeedSyncStatus.OK
        booking_crud.bulk_upsert_channel_bookings.assert_awaited_once()
        overbookings.add.assert_called_once_with(1)

    async def test_property_gone_records_error(self):
        feed = _feed_ref(content_hash="OLD")
        feed_crud = MagicMock()
        feed_crud.record_sync = AsyncMock()
        booking_crud = MagicMock()
        booking_crud.list_channel_bookings = AsyncMock()
        stack = _apply(
            _patched_orchestrator(
                events=[_event("u1", date(2026, 8, 1), date(2026, 8, 4))],
                feed_crud=feed_crud,
                booking_crud=booking_crud,
                property_data=None,
                hash_value="NEW",
            )
        )
        with stack:
            status = await sync_feed(feed)
        assert status == FeedSyncStatus.FETCH_ERROR
        booking_crud.list_channel_bookings.assert_not_called()

    async def test_parse_error_keeps_rows(self):
        from app.services.ical_parser import CalendarParseError

        feed = _feed_ref()
        feed_crud = MagicMock()
        feed_crud.record_sync = AsyncMock()
        booking_crud = MagicMock()
        booking_crud.list_channel_bookings = AsyncMock()
        with (
            patch(f"{SYNC}.fetch_ics", new=AsyncMock(return_value="garbage")),
            patch(f"{SYNC}.parse_ics", side_effect=CalendarParseError("bad")),
            patch(f"{SYNC}.calendar_feed_crud", new=feed_crud),
            patch(f"{SYNC}.booking_crud", new=booking_crud),
        ):
            status = await sync_feed(feed)
        assert status == FeedSyncStatus.PARSE_ERROR
        booking_crud.list_channel_bookings.assert_not_called()
        assert feed_crud.record_sync.await_args.kwargs["status"] == FeedSyncStatus.PARSE_ERROR

    async def test_update_cancel_truncate_applied(self):
        feed = _feed_ref(content_hash="OLD")
        u1, u2, u3 = uuid4(), uuid4(), uuid4()
        existing = [
            _existing("u1", date(2026, 9, 1), date(2026, 9, 3), bid=u1),  # dates change
            _existing("u2", date(2026, 8, 1), date(2026, 8, 4), bid=u2),  # vanished future → cancel
            _existing(
                "u3", date(2026, 7, 10), date(2026, 7, 15), bid=u3
            ),  # vanished midstay → truncate
        ]
        incoming = [_event("u1", date(2026, 9, 1), date(2026, 9, 5))]  # only u1 remains, extended
        feed_crud = MagicMock()
        feed_crud.record_sync = AsyncMock()
        booking_crud = _channel_booking_crud(existing=existing)
        stack = _apply(
            _patched_orchestrator(
                events=incoming,
                feed_crud=feed_crud,
                booking_crud=booking_crud,
                property_data={"owner_id": str(uuid4()), "currency": "EUR"},
                hash_value="NEW",
            )
        )
        with stack:
            status = await sync_feed(feed)
        assert status == FeedSyncStatus.OK
        booking_crud.bulk_set_channel_booking_dates.assert_awaited_once_with(
            [(u1, date(2026, 9, 1), date(2026, 9, 5))]
        )
        booking_crud.bulk_cancel_channel_bookings.assert_awaited_once_with([u2])
        booking_crud.bulk_truncate_channel_bookings.assert_awaited_once_with([(u3, TODAY)])
        booking_crud.bulk_upsert_channel_bookings.assert_not_called()  # no new UIDs


class TestSweep:
    async def test_sync_all_active_feeds_counts(self):
        feeds = [_feed_ref(), _feed_ref()]
        feed_crud = MagicMock()
        feed_crud.list_active = AsyncMock(return_value=feeds)
        with (
            patch(f"{SYNC}.calendar_feed_crud", new=feed_crud),
            patch(f"{SYNC}.sync_feed", new=AsyncMock(return_value=FeedSyncStatus.OK)),
            patch(f"{SYNC}.settings.calendar_sync_jitter_ms", 0),
        ):
            counts = await sync_all_active_feeds()
        assert counts["total"] == 2
        assert counts["ok"] == 2

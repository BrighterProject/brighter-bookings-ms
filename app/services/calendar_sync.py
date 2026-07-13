"""Import-only calendar sync engine (BTR-41).

Polls each active external feed, mirrors its reservations as read-only channel
``Booking`` rows, and frees dates when a reservation disappears — always failing
safe (never deleting occupancy we cannot re-verify). Brighter never publishes a
feed back to the channel, so it can never *cause* an overbooking penalty.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
from loguru import logger
from opentelemetry import metrics

from app import settings
from app.checkin_dispatch import today_in_sofia
from app.crud import booking_crud, calendar_feed_crud
from app.deps import PropertiesClient, _get_system_admin, get_properties_client
from app.feed_url import FeedUrlError, assert_host_is_public, validate_feed_url
from app.models import BookingChannel, BookingStatus, FeedSyncStatus
from app.schemas import BookingResponse
from app.services.ical_parser import (
    CalendarParseError,
    ParsedEvent,
    compute_content_hash,
    parse_ics,
)


class FeedLike(Protocol):
    """Structural view of an :class:`~app.models.ExternalCalendarFeed` the engine
    needs — satisfied by the ORM row and by test doubles alike."""

    id: UUID
    property_id: UUID
    channel: BookingChannel
    url: str
    content_hash: str | None


_MAX_REDIRECTS = 3

_meter = metrics.get_meter("brighter-bookings-ms")
_feeds_synced = _meter.create_counter("calendar_feeds_synced_total", description="Feeds synced OK")
_bookings_imported = _meter.create_counter(
    "channel_bookings_imported_total", description="Channel bookings created/updated"
)
_fetch_errors = _meter.create_counter(
    "calendar_feed_fetch_errors_total", description="Feed fetch/parse failures"
)
_overbookings = _meter.create_counter(
    "channel_overbookings_total", description="Imported reservations overlapping a platform booking"
)


# ---------------------------------------------------------------------------
# Fetch — manual, SSRF-revalidated redirect handling
# ---------------------------------------------------------------------------


class FeedFetchError(Exception):
    """Network/HTTP failure fetching a feed (recorded as fetch_error, fail-safe)."""


async def fetch_ics(url: str, timeout: float, channel: BookingChannel) -> str:
    """Fetch an iCal body, following redirects but re-validating every hop.

    Channels serve legitimate CDN/geo ``301/302``s, so we follow them — but at each
    hop we re-assert the target is on the channel's host allowlist **and** does not
    resolve to a private/link-local/loopback address before connecting. This keeps
    the SSRF allowlist intact across redirects. The body is streamed with a hard
    size cap so a hostile origin cannot OOM the pod. One retry on transient error.
    """
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return await _fetch_once(url, timeout, channel)
        except FeedUrlError:
            raise  # allowlist violation — not transient, do not retry
        except (httpx.HTTPError, FeedFetchError) as exc:
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(0.5)
    raise FeedFetchError(str(last_exc))


async def _read_capped_body(resp: httpx.Response) -> str:
    """Stream a response body into text, aborting past ``calendar_sync_max_bytes``.

    Checks the advertised ``Content-Length`` up front and, since that header is
    advisory, also enforces the cap on the bytes actually received.
    """
    max_bytes = settings.calendar_sync_max_bytes
    declared = resp.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise FeedFetchError(f"Feed body exceeds {max_bytes} bytes (declared {declared})")
    buffer = bytearray()
    async for chunk in resp.aiter_bytes():
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise FeedFetchError(f"Feed body exceeds {max_bytes} bytes")
    return buffer.decode(resp.charset_encoding or "utf-8", errors="replace")


async def _fetch_once(url: str, timeout: float, channel: BookingChannel) -> str:
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        current = url
        visited: set[str] = set()
        for _ in range(_MAX_REDIRECTS + 1):
            if current in visited:
                raise FeedFetchError("Cyclic redirect detected")
            visited.add(current)

            validate_feed_url(current, channel)  # scheme + host allowlist
            host = urlparse(current).hostname or ""
            await asyncio.to_thread(assert_host_is_public, host)  # private-IP denylist

            async with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FeedFetchError("Redirect without Location header")
                    current = urljoin(current, location)
                    continue
                resp.raise_for_status()
                return await _read_capped_body(resp)
        raise FeedFetchError("Too many redirects")


# ---------------------------------------------------------------------------
# Diff — pure function, the heart of the sync (thoroughly unit-tested)
# ---------------------------------------------------------------------------


@dataclass
class SyncActions:
    """What the sync must apply to reconcile existing rows with a fresh feed."""

    creates: list[ParsedEvent] = field(default_factory=list)
    # (booking_id, new_start, new_end) — also re-confirms a resurrected UID.
    updates: list[tuple[UUID, date, date]] = field(default_factory=list)
    cancels: list[UUID] = field(default_factory=list)
    # (booking_id, new_end=today) for mid-stay shortenings.
    truncations: list[tuple[UUID, date]] = field(default_factory=list)


def _overlaps_any(start: date, end: date, ranges: list[tuple[date, date]]) -> bool:
    """True if ``[start, end)`` overlaps any ``[s, e)`` in ``ranges`` (half-open)."""
    return any(start < e and end > s for s, e in ranges)


def diff_feed(
    existing: list[BookingResponse],
    incoming: list[ParsedEvent],
    today: date,
) -> SyncActions:
    """Reconcile imported bookings against a freshly-parsed feed.

    Vanished UIDs are resolved by ``end_date`` (not ``start_date``) to handle
    mid-stay cancellations without stranding future nights:

    - ``start_date >= today`` (nothing elapsed) → cancel;
    - ``start_date < today <= end_date`` (guest left early / stay shortened) → keep
      CONFIRMED, truncate ``end_date`` to today so elapsed nights stay recorded and
      future nights free up;
    - ``end_date < today`` (fully elapsed) → leave untouched. Booking.com prunes
      historical events, so a missing old UID means "aged out", not "cancelled" —
      cancelling would destroy historical occupancy ("the vanishing past").
    """
    actions = SyncActions()
    existing_by_uid = {b.external_uid: b for b in existing if b.external_uid is not None}
    incoming_by_uid: dict[str, ParsedEvent] = {ev.uid: ev for ev in incoming}

    for uid, ev in incoming_by_uid.items():
        cur = existing_by_uid.get(uid)
        if cur is None:
            actions.creates.append(ev)
        elif (
            cur.start_date != ev.start_date
            or cur.end_date != ev.end_date
            or cur.status != BookingStatus.CONFIRMED
        ):
            actions.updates.append((cur.id, ev.start_date, ev.end_date))
        # else: identical & already CONFIRMED → no write

    for uid, cur in existing_by_uid.items():
        if uid in incoming_by_uid:
            continue
        if cur.status != BookingStatus.CONFIRMED:
            continue  # already cancelled/terminal — nothing to free
        if cur.start_date >= today:
            actions.cancels.append(cur.id)
        elif cur.end_date > today:  # start < today <= end → mid-stay
            actions.truncations.append((cur.id, today))
        # else end_date <= today (fully elapsed) → leave untouched

    return actions


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def sync_feed(feed: FeedLike) -> FeedSyncStatus:
    """Sync one feed. ``feed`` needs ``.id .property_id .channel .url .content_hash``.

    Returns the recorded :class:`FeedSyncStatus`. Never raises — every failure path
    keeps existing imported rows (fail-safe) and records the error on the feed.
    """
    now = datetime.now(UTC)
    feed_id = feed.id
    property_id = feed.property_id

    # 1. Fetch
    try:
        body = await fetch_ics(feed.url, settings.calendar_sync_fetch_timeout, feed.channel)
    except (FeedFetchError, FeedUrlError, httpx.HTTPError) as exc:
        _fetch_errors.add(1, {"reason": "fetch"})
        logger.warning("Feed {} fetch failed — keeping existing rows: {}", feed_id, exc)
        await calendar_feed_crud.record_sync(
            feed_id, status=FeedSyncStatus.FETCH_ERROR, error=str(exc), synced_at=now
        )
        return FeedSyncStatus.FETCH_ERROR

    # 2. Parse
    try:
        events = parse_ics(body)
    except CalendarParseError as exc:
        _fetch_errors.add(1, {"reason": "parse"})
        logger.warning("Feed {} parse failed — keeping existing rows: {}", feed_id, exc)
        await calendar_feed_crud.record_sync(
            feed_id, status=FeedSyncStatus.PARSE_ERROR, error=str(exc), synced_at=now
        )
        return FeedSyncStatus.PARSE_ERROR

    content_hash = compute_content_hash(events)

    # 3. Short-circuit unchanged feeds (hash is over normalized events, so it is
    #    stable across DTSTAMP/PRODID churn).
    if content_hash == feed.content_hash:
        await calendar_feed_crud.record_sync(
            feed_id, status=FeedSyncStatus.OK, content_hash=content_hash, synced_at=now
        )
        _feeds_synced.add(1)
        return FeedSyncStatus.OK

    # 4. Resolve owner + currency once (system identity).
    admin = _get_system_admin()
    properties_client: PropertiesClient = get_properties_client()
    try:
        property_data = await properties_client.get_property(property_id, admin)
    except Exception as exc:  # upstream unreachable — treat as transient, keep rows
        _fetch_errors.add(1, {"reason": "properties"})
        logger.warning("Feed {} owner resolve failed — keeping rows: {}", feed_id, exc)
        await calendar_feed_crud.record_sync(
            feed_id, status=FeedSyncStatus.FETCH_ERROR, error=str(exc), synced_at=now
        )
        return FeedSyncStatus.FETCH_ERROR
    if not property_data:
        msg = "Property not found in properties-ms"
        await calendar_feed_crud.record_sync(
            feed_id, status=FeedSyncStatus.FETCH_ERROR, error=msg, synced_at=now
        )
        return FeedSyncStatus.FETCH_ERROR

    property_owner_id = UUID(property_data["owner_id"])
    currency = property_data.get("currency", "EUR")

    # 5. Diff against existing imported rows.
    existing = await booking_crud.list_channel_bookings(property_id, feed.channel)
    actions = diff_feed(existing, events, today_in_sofia())

    # 6. Apply — bulk. Each action group is a single round-trip regardless of feed
    #    size (a fresh feed with hundreds of reservations no longer means hundreds
    #    of inserts). The overbooking check fetches platform occupancy once, then
    #    flags overlaps in memory.
    if actions.creates:
        platform_ranges = await booking_crud.active_platform_ranges(property_id)
        for ev in actions.creates:
            if _overlaps_any(ev.start_date, ev.end_date, platform_ranges):
                _overbookings.add(1)
                logger.warning(
                    "Imported reservation {} overlaps a platform booking on property {} "
                    "[{}..{}) — recording anyway",
                    ev.uid,
                    property_id,
                    ev.start_date,
                    ev.end_date,
                )
        await booking_crud.bulk_upsert_channel_bookings(
            property_id=property_id,
            property_owner_id=property_owner_id,
            channel=feed.channel,
            currency=currency,
            events=actions.creates,
        )
    await booking_crud.bulk_set_channel_booking_dates(actions.updates)
    await booking_crud.bulk_cancel_channel_bookings(actions.cancels)
    await booking_crud.bulk_truncate_channel_bookings(actions.truncations)

    imported = len(actions.creates) + len(actions.updates)
    if imported:
        _bookings_imported.add(imported)

    # 7. Persist success + invalidate the public slots cache for the property.
    await calendar_feed_crud.record_sync(
        feed_id, status=FeedSyncStatus.OK, content_hash=content_hash, synced_at=now
    )
    from app.cache import invalidate_slots_cache

    await invalidate_slots_cache(property_id)
    _feeds_synced.add(1)
    logger.info(
        "Feed {} synced: {} imported, {} cancelled, {} truncated",
        feed_id,
        imported,
        len(actions.cancels),
        len(actions.truncations),
    )
    return FeedSyncStatus.OK


async def sync_all_active_feeds() -> dict[str, int]:
    """Sweep every active feed sequentially, with per-feed jitter.

    Sequential keeps the DB connection pool safe under a slow sweep; the k8s
    CronJob's ``concurrencyPolicy: Forbid`` guarantees sweeps never overlap.
    """
    feeds = await calendar_feed_crud.list_active()
    counts = {"total": len(feeds), "ok": 0, "fetch_error": 0, "parse_error": 0}
    jitter_max = settings.calendar_sync_jitter_ms / 1000.0
    for feed in feeds:
        status = await sync_feed(feed)
        counts[status.value] = counts.get(status.value, 0) + 1
        if jitter_max > 0:
            await asyncio.sleep(random.uniform(0, jitter_max))  # noqa: S311 — jitter, not crypto
    return counts

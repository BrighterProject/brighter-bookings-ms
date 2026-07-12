"""Parse Booking.com iCal exports into normalized date-range events (BTR-41).

Booking.com stay exports are all-day ``VALUE=DATE`` VEVENTs: timezone-less bare
dates where ``DTEND`` is the exclusive checkout day, mapping 1:1 to our
``start_date`` / ``end_date`` ``DateField``s. We defensively down-convert any
``DATE-TIME``/``TZID`` value to the property-local calendar date so a feed that
ever emits timed events does not drift ``end_date`` by a day.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar

# Booking dates are Bulgarian local calendar dates; a timed VEVENT is resolved
# against this zone before its date is taken.
_LOCAL_TZ = ZoneInfo("Europe/Sofia")


class CalendarParseError(ValueError):
    """Raised when an iCal body cannot be parsed into events."""


@dataclass(frozen=True)
class ParsedEvent:
    """One reservation/closure from a feed: an exclusive-end date range + its UID."""

    uid: str
    start_date: date
    end_date: date


def _to_local_date(value: object) -> date:
    """Map an iCal DTSTART/DTEND value to a bare local date.

    ``VALUE=DATE`` yields a ``date`` directly; a ``DATE-TIME`` is converted to
    Europe/Sofia first so the calendar date matches how bookings are stored.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(_LOCAL_TZ)
        return value.date()
    if isinstance(value, date):
        return value
    raise CalendarParseError(f"Unsupported date value: {value!r}")


def parse_ics(text: str) -> list[ParsedEvent]:
    """Parse an iCal body into events.

    VEVENTs without a UID are skipped (they cannot be diffed idempotently). A
    body that is not valid iCal, or a VEVENT missing DTSTART, raises
    :class:`CalendarParseError` so the caller can fail safe (keep existing rows).
    """
    try:
        cal = Calendar.from_ical(text)
    except (ValueError, TypeError) as exc:
        raise CalendarParseError(f"Malformed iCal body: {exc}") from exc

    events: list[ParsedEvent] = []
    for component in cal.walk("VEVENT"):
        uid = component.get("UID")
        dtstart = component.get("DTSTART")
        if uid is None or dtstart is None:
            continue
        start = _to_local_date(dtstart.dt)

        dtend = component.get("DTEND")
        # No DTEND on an all-day event ⇒ single night (exclusive end = next day).
        end = _to_local_date(dtend.dt) if dtend is not None else start + timedelta(days=1)

        # A zero/negative range is meaningless for occupancy — drop it.
        if end <= start:
            continue
        events.append(ParsedEvent(uid=str(uid), start_date=start, end_date=end))

    return events


def compute_content_hash(events: list[ParsedEvent]) -> str:
    """sha-256 over the *normalized* events, stable across DTSTAMP/PRODID churn.

    Hashing the sorted ``(uid, start, end)`` tuples — not the raw feed body, which
    changes on every fetch via its ``DTSTAMP`` header — lets the sweep short-circuit
    feeds whose actual reservations are unchanged.
    """
    normalized = sorted((e.uid, e.start_date.isoformat(), e.end_date.isoformat()) for e in events)
    blob = json.dumps(normalized, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()

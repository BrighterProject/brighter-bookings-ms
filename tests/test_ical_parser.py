"""Parser tests for Booking.com iCal exports (BTR-41).

Covers DTEND exclusivity, all-day events, multi-event feeds, missing-UID skip,
timed-event down-conversion, and normalized content-hash stability.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.ical_parser import (
    CalendarParseError,
    compute_content_hash,
    parse_ics,
)


def _feed(*vevents: str) -> str:
    body = "\n".join(vevents)
    return (
        "BEGIN:VCALENDAR\n"
        "PRODID:-//Booking.com//Booking.com//EN\n"
        "VERSION:2.0\n"
        "CALSCALE:GREGORIAN\n"
        f"{body}\n"
        "END:VCALENDAR\n"
    )


def _all_day(uid: str, start: str, end: str, dtstamp: str = "20260712T000000Z") -> str:
    return (
        "BEGIN:VEVENT\n"
        f"DTSTART;VALUE=DATE:{start}\n"
        f"DTEND;VALUE=DATE:{end}\n"
        "SUMMARY:CLOSED - Not available\n"
        f"UID:{uid}\n"
        f"DTSTAMP:{dtstamp}\n"
        "END:VEVENT"
    )


def test_all_day_dtend_is_exclusive_maps_directly():
    events = parse_ics(_feed(_all_day("a@booking.com", "20260712", "20260715")))
    assert len(events) == 1
    assert events[0].start_date == date(2026, 7, 12)
    # DTEND (checkout day) is exclusive and maps 1:1 to our end_date.
    assert events[0].end_date == date(2026, 7, 15)


def test_multi_event_feed():
    events = parse_ics(
        _feed(
            _all_day("a@booking.com", "20260712", "20260715"),
            _all_day("b@booking.com", "20260720", "20260722"),
        )
    )
    assert {e.uid for e in events} == {"a@booking.com", "b@booking.com"}


def test_vevent_without_uid_is_skipped():
    no_uid = (
        "BEGIN:VEVENT\n"
        "DTSTART;VALUE=DATE:20260712\n"
        "DTEND;VALUE=DATE:20260715\n"
        "DTSTAMP:20260712T000000Z\n"
        "END:VEVENT"
    )
    assert parse_ics(_feed(no_uid)) == []


def test_missing_dtend_defaults_to_single_night():
    single = (
        "BEGIN:VEVENT\n"
        "DTSTART;VALUE=DATE:20260712\n"
        "UID:s@booking.com\n"
        "DTSTAMP:20260712T000000Z\n"
        "END:VEVENT"
    )
    events = parse_ics(_feed(single))
    assert events[0].start_date == date(2026, 7, 12)
    assert events[0].end_date == date(2026, 7, 13)


def test_zero_or_negative_range_dropped():
    bad = _all_day("z@booking.com", "20260712", "20260712")  # end == start
    assert parse_ics(_feed(bad)) == []


def test_timed_event_downconverted_to_local_date():
    timed = (
        "BEGIN:VEVENT\n"
        "DTSTART:20260712T090000Z\n"  # 12:00 Europe/Sofia
        "DTEND:20260715T090000Z\n"
        "UID:t@booking.com\n"
        "DTSTAMP:20260712T000000Z\n"
        "END:VEVENT"
    )
    events = parse_ics(_feed(timed))
    assert events[0].start_date == date(2026, 7, 12)
    assert events[0].end_date == date(2026, 7, 15)


def test_malformed_body_raises_parse_error():
    with pytest.raises(CalendarParseError):
        parse_ics("this is not iCal at all {{{")


def test_content_hash_stable_across_dtstamp_change():
    a = parse_ics(_feed(_all_day("a@booking.com", "20260712", "20260715", "20260712T000000Z")))
    b = parse_ics(_feed(_all_day("a@booking.com", "20260712", "20260715", "20260712T090000Z")))
    # Hash is over normalized (uid,start,end) — DTSTAMP churn must not change it.
    assert compute_content_hash(a) == compute_content_hash(b)


def test_content_hash_differs_on_real_change():
    a = parse_ics(_feed(_all_day("a@booking.com", "20260712", "20260715")))
    b = parse_ics(_feed(_all_day("a@booking.com", "20260712", "20260716")))  # extended stay
    assert compute_content_hash(a) != compute_content_hash(b)


def test_content_hash_order_independent():
    e1 = _all_day("a@booking.com", "20260712", "20260715")
    e2 = _all_day("b@booking.com", "20260720", "20260722")
    assert compute_content_hash(parse_ics(_feed(e1, e2))) == compute_content_hash(
        parse_ics(_feed(e2, e1))
    )

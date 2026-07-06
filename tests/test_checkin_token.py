from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.checkin_token import CheckinTokenError, generate_checkin_token, verify_checkin_token


def test_generate_and_verify_round_trip():
    booking_id = uuid4()
    token = generate_checkin_token(booking_id, end_date=date.today() + timedelta(days=5))
    assert verify_checkin_token(token) == booking_id


def test_expired_token_raises():
    booking_id = uuid4()
    token = generate_checkin_token(
        booking_id, end_date=date.today() - timedelta(days=10), grace_days=1
    )
    with pytest.raises(CheckinTokenError):
        verify_checkin_token(token)


def test_tampered_token_raises():
    booking_id = uuid4()
    token = generate_checkin_token(booking_id, end_date=date.today() + timedelta(days=5))
    tampered = token[:-2] + "xx"
    with pytest.raises(CheckinTokenError):
        verify_checkin_token(tampered)


def test_same_claims_produce_a_deterministic_token():
    # No `iat`/nonce claim — HS256 signing of identical claims is deterministic.
    # GET /bookings/{id}/checkin-link relies on this to regenerate the same link
    # on demand without persisting the token.
    booking_id = uuid4()
    end_date = date(2026, 8, 1)
    token_a = generate_checkin_token(booking_id, end_date=end_date)
    token_b = generate_checkin_token(booking_id, end_date=end_date)
    assert token_a == token_b

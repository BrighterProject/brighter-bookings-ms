from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from jose import JWTError, jwt

from app import settings

_ALGORITHM = "HS256"


class CheckinTokenError(Exception):
    """Raised when a check-in token is missing, malformed, or expired."""


def _get_checkin_token_secret() -> str:
    secret = settings.checkin_token_secret
    if not secret:
        raise RuntimeError(
            "CHECKIN_TOKEN_SECRET is not set — required to sign/verify "
            "guest check-in links."
        )
    return secret


def generate_checkin_token(
    booking_id: UUID, end_date: date, grace_days: int | None = None
) -> str:
    grace = grace_days if grace_days is not None else settings.checkin_token_grace_days
    expiry = datetime.combine(end_date + timedelta(days=grace), time.min, tzinfo=UTC)
    claims = {"booking_id": str(booking_id), "exp": int(expiry.timestamp())}
    return jwt.encode(claims, _get_checkin_token_secret(), algorithm=_ALGORITHM)


def verify_checkin_token(token: str) -> UUID:
    try:
        claims = jwt.decode(token, _get_checkin_token_secret(), algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise CheckinTokenError("Invalid or expired check-in token") from exc
    try:
        return UUID(claims["booking_id"])
    except (KeyError, ValueError) as exc:
        raise CheckinTokenError("Malformed check-in token payload") from exc

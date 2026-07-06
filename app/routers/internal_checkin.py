from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app import settings
from app.checkin_token import generate_checkin_token
from app.deps import (
    NotificationsClient,
    UsersClient,
    _get_system_admin,
    get_notifications_client,
    get_users_client,
    verify_internal_cron_secret,
)
from app.models import Booking, BookingStatus, GuestIdentity

router = APIRouter(
    prefix="/internal/checkin",
    tags=["internal"],
    dependencies=[Depends(verify_internal_cron_secret)],
)

_SOFIA_TZ = ZoneInfo("Europe/Sofia")
_BATCH_SIZE = 100

# Fields nulled by the purge job — every GuestIdentity field except names,
# per BTR-15: only names survive after the ESTI reporting window.
_PURGE_FIELDS: tuple[str, ...] = (
    "date_of_birth",
    "gender",
    "citizenship",
    "document_type",
    "document_number",
    "document_issuing_country",
    "pin_egn",
)


def _today_in_sofia() -> date:
    # Booking.start_date/end_date are bare dates; the CronJob pod runs in UTC.
    # Resolving "today" to Bulgarian local time before comparing avoids the
    # dispatch/purge windows drifting by a day around UTC midnight.
    return datetime.now(_SOFIA_TZ).date()


@router.post("/dispatch")
async def dispatch_checkin_links(
    request: Request,
    users_client: UsersClient = Depends(get_users_client),
    notifications_client: NotificationsClient = Depends(get_notifications_client),
) -> dict[str, Any]:
    cutoff = _today_in_sofia() + timedelta(days=settings.checkin_dispatch_lead_days)
    caller = _get_system_admin()
    dispatched = 0

    while True:
        due = (
            await Booking.filter(
                start_date__lte=cutoff,
                status=BookingStatus.CONFIRMED,
                checkin_link_sent_at__isnull=True,
            )
            .limit(_BATCH_SIZE)
            .all()
        )
        if not due:
            break

        for booking in due:
            token = generate_checkin_token(booking.id, end_date=booking.end_date)
            recipients = await users_client.get_by_ids({booking.user_id}, caller)
            email = recipients[0]["email"] if recipients else None
            if email:
                await notifications_client.send(
                    to=email,
                    notification_type="checkin_link",
                    data={"token": token, "num_guests": booking.num_guests},
                )
            booking.checkin_link_sent_at = datetime.now(UTC)
            await booking.save(update_fields=["checkin_link_sent_at"])
            dispatched += 1

        if len(due) < _BATCH_SIZE:
            break

    return {"dispatched": dispatched}


@router.post("/purge")
async def purge_guest_identities(request: Request) -> dict[str, Any]:
    cutoff = _today_in_sofia() - timedelta(days=settings.booking_purge_window_days)
    purged_bookings = 0

    while True:
        due = (
            await Booking.filter(
                end_date__lte=cutoff,
                guest_data_purged_at__isnull=True,
            )
            .limit(_BATCH_SIZE)
            .all()
        )
        if not due:
            break

        for booking in due:
            await GuestIdentity.filter(booking_id=booking.id).update(
                **{field: None for field in _PURGE_FIELDS}
            )
            booking.guest_data_purged_at = datetime.now(UTC)
            await booking.save(update_fields=["guest_data_purged_at"])
            purged_bookings += 1

        if len(due) < _BATCH_SIZE:
            break

    return {"purged_bookings": purged_bookings}

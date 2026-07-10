from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from loguru import logger

from app import settings
from app.checkin_token import generate_checkin_token
from app.deps import CurrentUser, NotificationsClient, UsersClient, _get_system_admin
from app.models import Booking, BookingStatus

_SOFIA_TZ = ZoneInfo("Europe/Sofia")


def today_in_sofia() -> date:
    """Resolve "today" in Bulgarian local time.

    Booking dates are bare dates and the CronJob pod runs in UTC; anchoring the
    dispatch/purge windows to Europe/Sofia stops them drifting by a day around
    UTC midnight.
    """
    return datetime.now(_SOFIA_TZ).date()


def checkin_dispatch_cutoff() -> date:
    """Latest ``start_date`` eligible for a check-in link right now."""
    return today_in_sofia() + timedelta(days=settings.checkin_dispatch_lead_days)


async def send_checkin_link(
    booking: Booking,
    users_client: UsersClient,
    notifications_client: NotificationsClient,
    caller: CurrentUser,
) -> None:
    """Generate a check-in token, email it to the guest, and mark the booking sent.

    Claims the booking atomically (``UPDATE ... WHERE checkin_link_sent_at IS
    NULL``) before sending. The immediate post-confirm dispatch
    (:func:`maybe_send_checkin_link`, fired via ``asyncio.create_task`` and not
    awaited by the request handler) and the daily cron sweep both read-then-act
    on the same ``IS NULL`` marker; a plain "send, then mark sent" ordering
    lets both win the race and double-send. Claiming first makes only one
    caller proceed; if the send fails the claim is released so a later sweep
    retries.
    """
    claimed = await Booking.filter(
        id=booking.id, checkin_link_sent_at__isnull=True
    ).update(checkin_link_sent_at=datetime.now(UTC))
    if not claimed:
        return

    token = generate_checkin_token(booking.id, end_date=booking.end_date)
    recipients = await users_client.get_by_ids({booking.user_id}, caller)
    email = recipients[0]["email"] if recipients else None
    if email:
        try:
            await notifications_client.send(
                to=email,
                notification_type="checkin_link",
                data={"token": token, "num_guests": booking.num_guests},
            )
        except Exception:
            await Booking.filter(id=booking.id).update(checkin_link_sent_at=None)
            raise


async def maybe_send_checkin_link(
    booking_id: UUID,
    users_client: UsersClient,
    notifications_client: NotificationsClient,
) -> None:
    """Immediately dispatch a check-in link for a just-confirmed booking.

    Called on the ``CONFIRMED`` transition so short-notice bookings do not wait
    for the daily 08:00 sweep. The booking is reloaded fresh (the router holds a
    read-only schema, not the ORM row) and the send is a no-op when:

      - the booking vanished or is no longer ``CONFIRMED``;
      - a link was already sent (idempotent with the cron marker);
      - check-in is still beyond the dispatch lead window (the cron will pick it
        up closer to the date).
    """
    booking = await Booking.get_or_none(id=booking_id)
    if booking is None or booking.status != BookingStatus.CONFIRMED:
        return
    if booking.checkin_link_sent_at is not None:
        return
    if booking.start_date > checkin_dispatch_cutoff():
        return
    try:
        await send_checkin_link(
            booking, users_client, notifications_client, _get_system_admin()
        )
    except Exception:
        logger.exception(
            "Immediate check-in link dispatch failed for booking {}", booking_id
        )

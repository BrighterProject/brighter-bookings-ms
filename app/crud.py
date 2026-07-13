from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from ms_core import CRUD
from tortoise.transactions import in_transaction

from app.channels import channel_display_name
from app.models import (
    CHANNEL_GUEST_USER_ID,
    Booking,
    BookingChannel,
    BookingStatus,
    ExternalCalendarFeed,
    FeedSyncStatus,
)
from app.schemas import (
    BookingFilters,
    BookingResponse,
    BookingSlot,
    BookingStatusUpdate,
    CalendarFeedResponse,
)
from app.services.ical_parser import ParsedEvent


def _overlaps_unavailabilities(
    start: date,
    end: date,
    unavailabilities: list[dict],
) -> bool:
    """Return True if [start, end) overlaps any unavailability window."""
    for u in unavailabilities:
        u_start = date.fromisoformat(u["start_date"])
        u_end = date.fromisoformat(u["end_date"])
        if start < u_end and end > u_start:
            return True
    return False


class BookingCRUD(CRUD[Booking, BookingResponse]):  # type: ignore
    async def _has_db_conflict(
        self,
        property_id: UUID,
        start: date,
        end: date,
        exclude_id: UUID | None = None,
    ) -> bool:
        """Return True if an active booking overlaps the given window."""
        qs = Booking.filter(
            property_id=property_id,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
            start_date__lt=end,
            end_date__gt=start,
        )
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        return await qs.exists()

    async def create_booking(
        self,
        property_id: UUID,
        property_owner_id: UUID,
        user_id: UUID,
        start_date: date,
        end_date: date,
        price_per_night: Decimal,
        currency: str,
        num_guests: int,
        guest_name: str | None,
        guest_email: str | None,
        guest_phone: str | None,
        guest_country: str | None,
        special_requests: str | None,
        unavailabilities: list[dict],
        total_price: Decimal | None = None,
        gap_adjustment_pct: Decimal = Decimal("0"),
        payment_method: str | None = None,
    ) -> BookingResponse:
        """
        Persist a new booking after validating:
          - no DB conflict with existing active bookings (atomic, locked)
          - no overlap with property unavailability windows

        If ``total_price`` is provided (e.g. from the dynamic pricing resolver)
        it is stored directly; otherwise it is computed as price_per_night × nights.
        """
        # Check unavailabilities outside the transaction (no DB rows involved)
        if _overlaps_unavailabilities(start_date, end_date, unavailabilities):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking overlaps with a property unavailability period",
            )

        if total_price is None:
            num_nights = Decimal((end_date - start_date).days)
            total_price = (price_per_night * num_nights).quantize(Decimal("0.01"))

        # Atomic check-then-insert: SELECT FOR UPDATE prevents double-booking
        async with in_transaction():
            if (
                await Booking.filter(
                    property_id=property_id,
                    status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
                    start_date__lt=end_date,
                    end_date__gt=start_date,
                )
                .select_for_update()
                .exists()
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Booking conflicts with an existing booking for this property",
                )

            inst = await Booking.create(
                property_id=property_id,
                property_owner_id=property_owner_id,
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                price_per_night=price_per_night,
                total_price=total_price,
                currency=currency,
                num_guests=num_guests,
                guest_name=guest_name,
                guest_email=guest_email,
                guest_phone=guest_phone,
                guest_country=guest_country,
                special_requests=special_requests,
                gap_adjustment_pct=gap_adjustment_pct,
                payment_method=payment_method,
            )

        return BookingResponse.model_validate(inst, from_attributes=True)

    async def get_booking(
        self,
        booking_id: UUID,
        user_id: UUID | None = None,
        property_owner_id: UUID | None = None,
    ) -> BookingResponse | None:
        if user_id is not None:
            inst = await Booking.get_or_none(id=booking_id, user_id=user_id)
        elif property_owner_id is not None:
            inst = await Booking.get_or_none(id=booking_id, property_owner_id=property_owner_id)
        else:
            inst = await Booking.get_or_none(id=booking_id)

        if not inst:
            return None
        return BookingResponse.model_validate(inst, from_attributes=True)

    async def list_bookings(
        self,
        filters: BookingFilters,
        user_id: UUID | None = None,
        property_owner_id: UUID | None = None,
    ) -> list[BookingResponse]:
        qs = Booking.all()

        if user_id is not None:
            qs = qs.filter(user_id=user_id)
        if property_owner_id is not None:
            qs = qs.filter(property_owner_id=property_owner_id)
        if filters.property_id is not None:
            qs = qs.filter(property_id=filters.property_id)
        if filters.status is not None:
            qs = qs.filter(status=filters.status)

        offset = (filters.page - 1) * filters.page_size
        qs = qs.offset(offset).limit(filters.page_size)

        bookings = await qs
        return [BookingResponse.model_validate(b, from_attributes=True) for b in bookings]

    async def update_booking_status(
        self,
        booking_id: UUID,
        payload: BookingStatusUpdate,
    ) -> BookingResponse | None:
        inst = await Booking.get_or_none(id=booking_id)
        if not inst:
            return None
        inst.status = payload.status  # type: ignore
        await inst.save(update_fields=["status"])
        return BookingResponse.model_validate(inst, from_attributes=True)

    async def list_occupied_slots(self, property_id: UUID) -> list[BookingSlot]:
        """Return booked time windows for a property — no user info exposed."""
        bookings = await Booking.filter(
            property_id=property_id,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
        ).only("start_date", "end_date")
        return [BookingSlot.model_validate(b, from_attributes=True) for b in bookings]

    async def delete_booking(self, booking_id: UUID) -> bool:
        return await self.delete_by(id=booking_id)

    # -- Channel imports (BTR-41) ------------------------------------------
    # These bypass the API status-transition rules by design: the sync engine
    # owns the lifecycle of imported (booking_com) rows, so it writes their
    # fields directly rather than going through _assert_transition.

    async def list_channel_bookings(
        self, property_id: UUID, channel: BookingChannel
    ) -> list[BookingResponse]:
        """All imported bookings for a property/channel, keyed later by external_uid."""
        rows = await Booking.filter(property_id=property_id, channel=channel)
        return [BookingResponse.model_validate(b, from_attributes=True) for b in rows]

    async def active_platform_ranges(self, property_id: UUID) -> list[tuple[date, date]]:
        """``(start, end)`` of every active *platform* booking for a property.

        Fetched once per sync so the overbooking check for a whole feed is a single
        query instead of one per incoming reservation.
        """
        rows = await Booking.filter(
            property_id=property_id,
            channel=BookingChannel.PLATFORM,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
        ).values_list("start_date", "end_date")
        return [(start, end) for start, end in rows]

    async def bulk_upsert_channel_bookings(
        self,
        *,
        property_id: UUID,
        property_owner_id: UUID,
        channel: BookingChannel,
        currency: str,
        events: list[ParsedEvent],
    ) -> None:
        """Insert freshly-seen imported reservations in a single round-trip.

        ``events`` are the feed's genuinely-new UIDs (the diff already excluded
        existing ones). ``ignore_conflicts`` keeps the write idempotent against the
        ``(property_id, channel, external_uid)`` unique constraint should a manual
        sync race the cron sweep — the next sweep reconciles any skipped row.
        """
        if not events:
            return
        guest_name = channel_display_name(channel)
        rows = [
            Booking(
                property_id=property_id,
                property_owner_id=property_owner_id,
                user_id=CHANNEL_GUEST_USER_ID,
                channel=channel,
                external_uid=ev.uid,
                start_date=ev.start_date,
                end_date=ev.end_date,
                status=BookingStatus.CONFIRMED,
                price_per_night=Decimal("0"),
                total_price=Decimal("0"),
                currency=currency,
                num_guests=1,
                guest_name=guest_name,
            )
            for ev in events
        ]
        await Booking.bulk_create(rows, ignore_conflicts=True)

    async def bulk_set_channel_booking_dates(
        self, updates: list[tuple[UUID, date, date]]
    ) -> None:
        """Apply date changes to imported bookings in one statement.

        Also re-confirms a resurrected UID (status back to CONFIRMED).
        """
        if not updates:
            return
        rows = [
            Booking(id=bid, start_date=start, end_date=end, status=BookingStatus.CONFIRMED)
            for bid, start, end in updates
        ]
        await Booking.bulk_update(rows, fields=["start_date", "end_date", "status"])

    async def bulk_cancel_channel_bookings(self, booking_ids: list[UUID]) -> None:
        """CANCEL every listed imported booking — their UIDs vanished before check-in."""
        if not booking_ids:
            return
        await Booking.filter(id__in=booking_ids).update(status=BookingStatus.CANCELLED)

    async def bulk_truncate_channel_bookings(self, truncations: list[tuple[UUID, date]]) -> None:
        """Shorten mid-stay imported bookings so future nights free up for resale.

        Grouped by target ``end_date`` (the sweep truncates every mid-stay row to
        ``today``, so this is normally a single UPDATE).
        """
        if not truncations:
            return
        by_end: dict[date, list[UUID]] = defaultdict(list)
        for bid, new_end in truncations:
            by_end[new_end].append(bid)
        for new_end, ids in by_end.items():
            await Booking.filter(id__in=ids).update(end_date=new_end)


booking_crud = BookingCRUD(Booking, BookingResponse)


class CalendarFeedCRUD:
    """DB operations for external iCal feeds (BTR-41)."""

    async def list_for_property(self, property_id: UUID) -> list[CalendarFeedResponse]:
        rows = await ExternalCalendarFeed.filter(property_id=property_id)
        return [CalendarFeedResponse.model_validate(f, from_attributes=True) for f in rows]

    async def create(
        self, property_id: UUID, channel: BookingChannel, url: str
    ) -> CalendarFeedResponse:
        inst = await ExternalCalendarFeed.create(property_id=property_id, channel=channel, url=url)
        return CalendarFeedResponse.model_validate(inst, from_attributes=True)

    async def get(self, feed_id: UUID) -> ExternalCalendarFeed | None:
        return await ExternalCalendarFeed.get_or_none(id=feed_id)

    async def delete(self, feed_id: UUID) -> bool:
        deleted = await ExternalCalendarFeed.filter(id=feed_id).delete()
        return bool(deleted)

    async def list_active(self) -> list[ExternalCalendarFeed]:
        """All feeds the sweep should poll — ORM rows so the engine can read/write hash."""
        return await ExternalCalendarFeed.filter(is_active=True)

    async def record_sync(
        self,
        feed_id: UUID,
        *,
        status: FeedSyncStatus,
        content_hash: str | None = None,
        error: str | None = None,
        synced_at: datetime,
    ) -> None:
        """Persist the outcome of a sync attempt.

        ``content_hash`` is only advanced on a successful parse; on error it is
        left as-is so the next sweep re-processes the feed rather than short-circuiting.
        """
        updates: dict[str, object] = {
            "last_status": status,
            "last_error": (error[:1024] if error else None),
            "last_synced_at": synced_at,
        }
        if content_hash is not None:
            updates["content_hash"] = content_hash
        await ExternalCalendarFeed.filter(id=feed_id).update(**updates)


calendar_feed_crud = CalendarFeedCRUD()

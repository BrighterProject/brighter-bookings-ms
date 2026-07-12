from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from ms_core import CRUD
from tortoise.transactions import in_transaction

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

    async def has_platform_conflict(self, property_id: UUID, start: date, end: date) -> bool:
        """True if an active *platform* booking overlaps [start, end).

        Used to flag an incoming channel reservation that overbooks a stay already
        sold on Brighter — recorded anyway, but surfaced via log + metric.
        """
        return await Booking.filter(
            property_id=property_id,
            channel=BookingChannel.PLATFORM,
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
            start_date__lt=end,
            end_date__gt=start,
        ).exists()

    async def upsert_channel_booking(
        self,
        *,
        property_id: UUID,
        property_owner_id: UUID,
        channel: BookingChannel,
        external_uid: str,
        start_date: date,
        end_date: date,
        currency: str,
    ) -> tuple[BookingResponse, bool]:
        """Create or refresh an imported booking, idempotent on (property, channel, uid).

        The unique constraint on ``(property_id, channel, external_uid)`` makes a
        re-import a no-op / update rather than a duplicate.
        """
        inst, created = await Booking.update_or_create(
            property_id=property_id,
            channel=channel,
            external_uid=external_uid,
            defaults={
                "property_owner_id": property_owner_id,
                "user_id": CHANNEL_GUEST_USER_ID,
                "start_date": start_date,
                "end_date": end_date,
                "status": BookingStatus.CONFIRMED,
                "price_per_night": Decimal("0"),
                "total_price": Decimal("0"),
                "currency": currency,
                "num_guests": 1,
                "guest_name": "Booking.com",
            },
        )
        return BookingResponse.model_validate(inst, from_attributes=True), created

    async def set_channel_booking_dates(
        self, booking_id: UUID, start_date: date, end_date: date
    ) -> None:
        """Update an imported booking's dates (also re-confirms a resurrected UID)."""
        await Booking.filter(id=booking_id).update(
            start_date=start_date, end_date=end_date, status=BookingStatus.CONFIRMED
        )

    async def cancel_channel_booking(self, booking_id: UUID) -> None:
        """Mark an imported booking CANCELLED — its UID vanished before check-in."""
        await Booking.filter(id=booking_id).update(status=BookingStatus.CANCELLED)

    async def truncate_channel_booking(self, booking_id: UUID, new_end: date) -> None:
        """Shorten a mid-stay imported booking so future nights free up for resale."""
        await Booking.filter(id=booking_id).update(end_date=new_end)


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

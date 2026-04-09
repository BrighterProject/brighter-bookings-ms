from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from ms_core import CRUD
from tortoise.transactions import in_transaction

from app.models import Booking, BookingStatus
from app.schemas import BookingFilters, BookingResponse, BookingSlot, BookingStatusUpdate


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
        guest_name: str | None,
        guest_email: str | None,
        guest_phone: str | None,
        special_requests: str | None,
        unavailabilities: list[dict],
    ) -> BookingResponse:
        """
        Persist a new booking after validating:
          - no DB conflict with existing active bookings (atomic, locked)
          - no overlap with property unavailability windows
        """
        # Check unavailabilities outside the transaction (no DB rows involved)
        if _overlaps_unavailabilities(start_date, end_date, unavailabilities):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking overlaps with a property unavailability period",
            )

        num_nights = Decimal((end_date - start_date).days)
        total_price = (price_per_night * num_nights).quantize(Decimal("0.01"))

        # Atomic check-then-insert: SELECT FOR UPDATE prevents double-booking
        async with in_transaction():
            if await Booking.filter(
                property_id=property_id,
                status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED],
                start_date__lt=end_date,
                end_date__gt=start_date,
            ).select_for_update().exists():
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
                guest_name=guest_name,
                guest_email=guest_email,
                guest_phone=guest_phone,
                special_requests=special_requests,
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
            inst = await Booking.get_or_none(
                id=booking_id, property_owner_id=property_owner_id
            )
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
        return [
            BookingResponse.model_validate(b, from_attributes=True) for b in bookings
        ]

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


booking_crud = BookingCRUD(Booking, BookingResponse)

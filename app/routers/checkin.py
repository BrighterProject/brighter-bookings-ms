from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger

from app.deps import (
    PropertiesClient,
    _get_system_admin,
    get_booking_from_checkin_token,
    get_properties_client,
)
from app.limiter import limiter
from app.models import Booking, GuestIdentity
from app.schemas import GuestIdentityCreate, GuestRosterResponse, GuestRosterSlot

router = APIRouter(prefix="/checkin", tags=["checkin"])


@router.get("/{token}", response_model=GuestRosterResponse)
@limiter.limit("30/minute")
async def get_checkin_roster(
    request: Request,
    booking: Booking = Depends(get_booking_from_checkin_token),
    properties_client: PropertiesClient = Depends(get_properties_client),
) -> GuestRosterResponse:
    property_data = await properties_client.get_property(booking.property_id, _get_system_admin())
    existing = await GuestIdentity.filter(booking_id=booking.id).order_by("created_at").all()

    roster: list[GuestRosterSlot] = []
    for i in range(booking.num_guests):
        if i < len(existing):
            g = existing[i]
            roster.append(
                GuestRosterSlot(
                    filled=True,
                    first_name=g.first_name,
                    middle_name=g.middle_name,
                    last_name=g.last_name,
                    guest_id=g.id,
                )
            )
        else:
            roster.append(GuestRosterSlot(filled=False))

    return GuestRosterResponse(
        property_name=(property_data or {}).get("name", ""),
        property_city=(property_data or {}).get("city"),
        start_date=booking.start_date,
        end_date=booking.end_date,
        total_slots=booking.num_guests,
        filled_slots=len(existing),
        roster=roster,
    )


@router.post("/{token}/guests", response_model=GuestRosterSlot, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def add_guest_identity(
    request: Request,
    payload: GuestIdentityCreate,
    booking: Booking = Depends(get_booking_from_checkin_token),
) -> GuestRosterSlot:
    existing_count = await GuestIdentity.filter(booking_id=booking.id).count()
    if existing_count >= booking.num_guests:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All guest slots for this booking are already filled",
        )
    created = await GuestIdentity.create(booking=booking, **payload.model_dump())
    return GuestRosterSlot(
        filled=True,
        first_name=created.first_name,
        middle_name=created.middle_name,
        last_name=created.last_name,
        guest_id=created.id,
    )


@router.delete("/{token}/guests/{guest_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def clear_guest_identity(
    request: Request,
    guest_id: UUID,
    booking: Booking = Depends(get_booking_from_checkin_token),
) -> None:
    deleted_count = await GuestIdentity.filter(id=guest_id, booking_id=booking.id).delete()
    if deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest slot not found")
    logger.bind(
        audit=True,
        action="guest_cleared",
        ip=request.client.host if request.client else None,
        booking_id=str(booking.id),
        guest_id=str(guest_id),
    ).info("guest_identity_cleared")

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger

from app.deps import (
    CurrentUser,
    can_admin_write_guest_identity,
    can_view_guest_identities,
    get_current_user,
)
from app.limiter import limiter
from app.models import Booking, BookingStatus, GuestIdentity
from app.schemas import GuestIdentityCreate, GuestIdentityResponse

router = APIRouter(prefix="/bookings", tags=["guest-identities"])


@router.post(
    "/{booking_id}/guests",
    response_model=GuestIdentityResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def admin_add_guest_identity(
    request: Request,
    booking_id: UUID,
    payload: GuestIdentityCreate,
    current_user: CurrentUser = Depends(can_admin_write_guest_identity),
) -> GuestIdentityResponse:
    booking = await Booking.get_or_none(id=booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot add guests to a cancelled/completed/no-show booking",
        )
    created = await GuestIdentity.create(booking=booking, **payload.model_dump())
    logger.bind(
        audit=True,
        action="guest_added_by_admin",
        actor_id=str(current_user.id),
        booking_id=str(booking_id),
    ).info("guest_identity_added")
    return GuestIdentityResponse.model_validate(created, from_attributes=True)


@router.get("/{booking_id}/guests", response_model=list[GuestIdentityResponse])
@limiter.limit("200/minute")
async def list_guest_identities(
    request: Request,
    booking_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    booking: Booking = Depends(can_view_guest_identities),
) -> list[GuestIdentityResponse]:
    guests = await GuestIdentity.filter(booking_id=booking.id).order_by("created_at").all()
    logger.bind(
        audit=True,
        actor_id=str(current_user.id),
        actor_scopes=current_user.scopes,
        booking_id=str(booking_id),
    ).info("guest_identity_access")
    return [GuestIdentityResponse.model_validate(g, from_attributes=True) for g in guests]


@router.delete("/{booking_id}/guests/{guest_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def admin_delete_guest_identity(
    request: Request,
    booking_id: UUID,
    guest_id: UUID,
    current_user: CurrentUser = Depends(can_admin_write_guest_identity),
) -> None:
    deleted_count = await GuestIdentity.filter(id=guest_id, booking_id=booking_id).delete()
    if deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    logger.bind(
        audit=True,
        action="guest_deleted_by_admin",
        actor_id=str(current_user.id),
        booking_id=str(booking_id),
    ).info("guest_identity_deleted")

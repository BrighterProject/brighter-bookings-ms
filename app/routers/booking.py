import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger

from app.cache import get_slots_cache, invalidate_slots_cache, set_slots_cache
from app.crud import booking_crud
from app.limiter import limiter
from app.deps import (
    CurrentUser,
    NotificationsClient,
    PaymentsClient,
    UsersClient,
    PropertiesClient,
    _get_system_admin,
    can_admin_delete_booking,
    can_read_or_manage_booking,
    can_write_booking,
    get_current_user,
    get_notifications_client,
    get_payments_client,
    get_users_client,
    get_properties_client,
)
from app.schemas import (
    BookingCreate,
    BookingEnriched,
    BookingFilters,
    BookingResponse,
    BookingSlot,
    BookingStatus,
    BookingStatusUpdate,
)
from app.scopes import BookingScope

router = APIRouter(prefix="/bookings", tags=["bookings"])


# ---------------------------------------------------------------------------
# Enrichment helper
# ---------------------------------------------------------------------------


async def _enrich(
    bookings: list,
    current_user: CurrentUser,
    properties_client: PropertiesClient,
    users_client: UsersClient,
) -> list[BookingEnriched]:
    """
    Convert a list of raw booking objects into BookingEnriched by fetching
    property names and user names from upstream services in parallel.
    Both upstream calls degrade gracefully — enriched fields become None on error.
    """
    if not bookings:
        return []

    parsed = [BookingResponse.model_validate(b, from_attributes=True) for b in bookings]

    property_ids = {b.property_id for b in parsed}
    user_ids = {b.user_id for b in parsed} | {b.property_owner_id for b in parsed}

    properties_raw, users_raw = await asyncio.gather(
        properties_client.get_by_ids(property_ids, current_user),
        users_client.get_by_ids(user_ids, current_user),
    )

    property_map: dict[str, str | None] = {v["id"]: v.get("name") for v in properties_raw}
    user_map: dict[str, dict] = {
        u["id"]: {"username": u.get("username"), "full_name": u.get("full_name")}
        for u in users_raw
    }

    result = []
    for b in parsed:
        customer = user_map.get(str(b.user_id), {})
        owner = user_map.get(str(b.property_owner_id), {})
        result.append(
            BookingEnriched(
                **b.model_dump(),
                property_name=property_map.get(str(b.property_id)),
                customer_username=customer.get("username"),
                customer_full_name=customer.get("full_name"),
                owner_username=owner.get("username"),
                owner_full_name=owner.get("full_name"),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Notification helpers (fire-and-forget via asyncio.create_task)
# ---------------------------------------------------------------------------


def _resolve_property_name(property_dict: dict) -> str | None:
    """Extract property name from a PropertyResponse dict (en preferred, then bg, then ru)."""
    for locale in ("en", "bg", "ru"):
        for t in property_dict.get("translations", []):
            if t.get("locale") == locale and t.get("name"):
                return t["name"]
    return None


async def _notify_booking_created(
    booking,
    property_name: str | None,
    users_client: UsersClient,
    nc: NotificationsClient,
) -> None:
    admin = _get_system_admin()
    users = await users_client.get_by_ids(
        {booking.property_owner_id}, admin
    )
    owner_email: str | None = users[0].get("email") if users else None

    prop_label = property_name or "Your property"
    start_date_formatted = booking.start_date.strftime("%b %d")
    end_date_formatted = booking.end_date.strftime("%b %d")
    data = {
        "property_name": prop_label,
        "start_date": start_date_formatted,
        "end_date": end_date_formatted,
        "booking_id": str(booking.id),
        "property_id": str(booking.property_id),
    }

    coros = []
    if booking.guest_email:
        coros.append(nc.send(
            to=booking.guest_email,
            notification_type="booking_created_guest",
            data=data,
        ))
    if owner_email:
        coros.append(nc.send(
            to=owner_email,
            notification_type="booking_created_owner",
            data=data,
        ))
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)


async def _notify_booking_status_changed(
    booking,
    new_status: BookingStatus,
    users_client: UsersClient,
    nc: NotificationsClient,
) -> None:
    guest_email: str | None = getattr(booking, "guest_email", None)
    if not guest_email:
        admin = _get_system_admin()
        users = await users_client.get_by_ids({booking.user_id}, admin)
        guest_email = users[0].get("email") if users else None

    if not guest_email:
        return

    if new_status == BookingStatus.CONFIRMED:
        await nc.send(
            to=guest_email,
            notification_type="booking_confirmed",
        )
    elif new_status == BookingStatus.CANCELLED:
        await nc.send(
            to=guest_email,
            notification_type="booking_cancelled",
        )


# ---------------------------------------------------------------------------
# Transition guard helpers
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[BookingStatus, set[BookingStatus]] = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
    },
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.NO_SHOW: set(),
}

# Which scope is required (on top of the valid-transition check) per target status
_MANAGE_STATUSES = {
    BookingStatus.CONFIRMED,
    BookingStatus.COMPLETED,
    BookingStatus.NO_SHOW,
}
_CANCEL_STATUSES = {BookingStatus.CANCELLED}


def _assert_transition(
    old_status: BookingStatus,
    new_status: BookingStatus,
    booking_user_id: UUID,
    booking_property_owner_id: UUID,
    current_user: CurrentUser,
) -> None:
    """
    Raise HTTP 400/403 if the transition is invalid or the caller lacks permission.

    Rules:
      pending  → confirmed  : MANAGE + property owner, OR admin
      pending  → cancelled  : CANCEL + booker, OR MANAGE + property owner, OR admin
      confirmed → completed  : MANAGE + property owner, OR admin
      confirmed → cancelled  : CANCEL + booker, OR MANAGE + property owner, OR admin
      confirmed → no_show    : MANAGE + property owner, OR admin
    """
    if new_status not in _VALID_TRANSITIONS.get(old_status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot transition from '{old_status}' to '{new_status}'. "
                "Allowed: "
                f"{[s.value for s in _VALID_TRANSITIONS.get(old_status, set())]}"
            ),
        )

    is_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_WRITE in current_user.scopes
    )
    if is_admin:
        return

    is_property_owner = current_user.id == booking_property_owner_id
    has_manage = BookingScope.MANAGE in current_user.scopes

    if new_status in _MANAGE_STATUSES:
        if not (has_manage and is_property_owner):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Transitioning to '{new_status}' requires "
                    f"'{BookingScope.MANAGE}' scope and being the property owner."
                ),
            )

    elif new_status in _CANCEL_STATUSES:
        is_booker = current_user.id == booking_user_id
        has_cancel = BookingScope.CANCEL in current_user.scopes
        # Either the customer cancels their own booking, or the property owner refuses it
        if not ((has_cancel and is_booker) or (has_manage and is_property_owner)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Transitioning to '{new_status}' requires "
                    f"'{BookingScope.CANCEL}' scope as the booking owner, "
                    f"or '{BookingScope.MANAGE}' scope as the property owner."
                ),
            )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/occupied-property-ids", response_model=list[UUID])
@limiter.limit("120/minute")
async def get_occupied_property_ids(
    request: Request,
    from_date: date = Query(...),
    to_date: date = Query(...),
) -> list[UUID]:
    """
    Internal endpoint: returns distinct property IDs that have PENDING or CONFIRMED
    bookings overlapping [from_date, to_date). Used by properties-ms availability search.
    Public — no auth required (property IDs are not sensitive).
    """
    from app.models import Booking, BookingStatus as BS

    property_ids = await Booking.filter(
        status__in=[BS.PENDING, BS.CONFIRMED],
        start_date__lt=to_date,
        end_date__gt=from_date,
    ).values_list("property_id", flat=True)
    return list(set(property_ids))


@router.get("/slots", response_model=list[BookingSlot])
@limiter.limit("60/minute")
async def get_property_slots(
    request: Request,
    property_id: UUID,
) -> list[BookingSlot]:
    """
    Returns occupied time windows for a property.
    Public endpoint — response contains NO user identity.
    Rate limited to 60 requests/minute per IP.
    """
    cached = await get_slots_cache(property_id)
    if cached is not None:
        logger.debug("Cache hit for slots: property_id={}", property_id)
        return [BookingSlot(**s) for s in cached]

    logger.debug("Cache miss for slots: property_id={}", property_id)
    slots = await booking_crud.list_occupied_slots(property_id)
    await set_slots_cache(property_id, [s.model_dump(mode="json") for s in slots])
    return slots


@router.get("/", response_model=list[BookingEnriched])
@limiter.limit("200/minute")
async def list_bookings(
    request: Request,
    filters: BookingFilters = Depends(),
    current_user: CurrentUser = Depends(can_read_or_manage_booking),
    properties_client: PropertiesClient = Depends(get_properties_client),
    users_client: UsersClient = Depends(get_users_client),
) -> list[BookingEnriched]:
    is_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_READ in current_user.scopes
    )
    is_manager = BookingScope.MANAGE in current_user.scopes
    is_reader = BookingScope.READ in current_user.scopes

    if is_admin:
        bookings = await booking_crud.list_bookings(filters=filters)
    elif is_manager:
        # Property owners see bookings for their properties regardless of also having
        # bookings:read (which DEFAULT_OWNER_SCOPES includes for customer use)
        bookings = await booking_crud.list_bookings(
            filters=filters, property_owner_id=current_user.id
        )
    else:
        bookings = await booking_crud.list_bookings(
            filters=filters, user_id=current_user.id
        )

    return await _enrich(bookings, current_user, properties_client, users_client)


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_booking(
    request: Request,
    payload: BookingCreate,
    current_user: CurrentUser = Depends(can_write_booking),
    properties_client: PropertiesClient = Depends(get_properties_client),
    users_client: UsersClient = Depends(get_users_client),
    notifications_client: NotificationsClient = Depends(get_notifications_client),
) -> BookingResponse:
    # 1. Validate property exists and is ACTIVE
    property = await properties_client.get_property(payload.property_id, current_user)
    if property is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        )
    if property.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Property is not available for booking (status: {property.get('status')})"
            ),
        )

    # 2. Fetch unavailabilities and check for conflicts in CRUD
    unavailabilities = await properties_client.get_unavailabilities(
        payload.property_id, current_user
    )

    booking = await booking_crud.create_booking(
        property_id=payload.property_id,
        property_owner_id=UUID(property["owner_id"]),
        user_id=current_user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        price_per_night=Decimal(str(property["price_per_night"])),
        currency=property.get("currency", "EUR"),
        guest_name=payload.guest_name,
        guest_email=payload.guest_email,
        guest_phone=payload.guest_phone,
        special_requests=payload.special_requests,
        unavailabilities=unavailabilities,
    )
    await invalidate_slots_cache(payload.property_id)
    asyncio.create_task(
        _notify_booking_created(
            booking,
            property_name=_resolve_property_name(property),
            users_client=users_client,
            nc=notifications_client,
        )
    )
    return booking


@router.get("/{booking_id}", response_model=BookingEnriched)
@limiter.limit("200/minute")
async def get_booking(
    request: Request,
    booking_id: UUID,
    current_user: CurrentUser = Depends(can_read_or_manage_booking),
    properties_client: PropertiesClient = Depends(get_properties_client),
    users_client: UsersClient = Depends(get_users_client),
) -> BookingEnriched:
    is_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_READ in current_user.scopes
    )
    is_manager = BookingScope.MANAGE in current_user.scopes
    is_reader = BookingScope.READ in current_user.scopes

    if is_admin:
        booking = await booking_crud.get_booking(booking_id)
    elif is_manager:
        booking = await booking_crud.get_booking(
            booking_id, property_owner_id=current_user.id
        )
    else:
        booking = await booking_crud.get_booking(booking_id, user_id=current_user.id)

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    results = await _enrich([booking], current_user, properties_client, users_client)
    return results[0]


@router.patch("/{booking_id}/status", response_model=BookingResponse)
@limiter.limit("60/minute")
async def update_booking_status(
    request: Request,
    booking_id: UUID,
    payload: BookingStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    payments_client: PaymentsClient = Depends(get_payments_client),
    users_client: UsersClient = Depends(get_users_client),
    notifications_client: NotificationsClient = Depends(get_notifications_client),
) -> BookingResponse:
    # Fetch the booking without ownership filter — we validate permissions manually
    booking = await booking_crud.get_booking(booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    _assert_transition(
        old_status=booking.status,
        new_status=payload.status,
        booking_user_id=booking.user_id,
        booking_property_owner_id=booking.property_owner_id,
        current_user=current_user,
    )

    updated = await booking_crud.update_booking_status(booking_id, payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

    await invalidate_slots_cache(booking.property_id)

    # Trigger Stripe refund when the property owner (or admin) cancels a paid booking.
    # Customer cancellations do NOT refund — per the no-refund policy for customers.
    # Failure to refund does not block the cancellation response.
    if payload.status == BookingStatus.CANCELLED:
        is_admin = (
            BookingScope.ADMIN in current_user.scopes
            or BookingScope.ADMIN_WRITE in current_user.scopes
        )
        is_property_owner = current_user.id == booking.property_owner_id
        if is_admin or is_property_owner:
            await payments_client.refund_booking(booking_id, current_user)

    if payload.status in {BookingStatus.CONFIRMED, BookingStatus.CANCELLED}:
        asyncio.create_task(
            _notify_booking_status_changed(
                booking, payload.status, users_client, notifications_client
            )
        )

    return updated


@router.delete(
    "/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(can_admin_delete_booking)],
)
@limiter.limit("60/minute")
async def delete_booking(request: Request, booking_id: UUID) -> None:
    deleted = await booking_crud.delete_booking(booking_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found"
        )

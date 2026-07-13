"""Owner-facing external calendar feed management (BTR-41).

Nested under ``/bookings/*`` so no Traefik route changes are needed. All routes
require ``bookings:manage`` (or admin) plus per-property ownership. URLs are
SSRF-guarded at the schema layer (``https://*.booking.com`` only); redirects are
re-validated per hop at fetch time.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from loguru import logger

from app.crud import calendar_feed_crud
from app.deps import (
    CurrentUser,
    PropertiesClient,
    get_current_user,
    get_properties_client,
)
from app.limiter import limiter
from app.schemas import CalendarFeedCreate, CalendarFeedResponse
from app.scopes import BookingScope
from app.services.calendar_sync import sync_feed

router = APIRouter(prefix="/bookings/calendar-feeds", tags=["calendar-feeds"])


def _is_admin(user: CurrentUser) -> bool:
    return user.is_admin or BookingScope.ADMIN in user.scopes


async def _require_manage_or_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Gate: property owners (bookings:manage) or admins only."""
    if BookingScope.MANAGE in current_user.scopes or _is_admin(current_user):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Requires '{BookingScope.MANAGE}' scope (property owners) or admin.",
    )


async def _assert_property_owner(
    property_id: UUID,
    current_user: CurrentUser,
    properties_client: PropertiesClient,
) -> None:
    """Ensure the caller owns ``property_id`` (admins pass through)."""
    if _is_admin(current_user):
        return
    property_data = await properties_client.get_property(property_id, current_user)
    if property_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    if UUID(property_data["owner_id"]) != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this property.",
        )


@router.get("", response_model=list[CalendarFeedResponse])
@limiter.limit("60/minute")
async def list_feeds(
    request: Request,
    property_id: UUID = Query(...),
    current_user: CurrentUser = Depends(_require_manage_or_admin),
    properties_client: PropertiesClient = Depends(get_properties_client),
) -> list[CalendarFeedResponse]:
    await _assert_property_owner(property_id, current_user, properties_client)
    return await calendar_feed_crud.list_for_property(property_id)


@router.post("", response_model=CalendarFeedResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_feed(
    request: Request,
    payload: CalendarFeedCreate,
    current_user: CurrentUser = Depends(_require_manage_or_admin),
    properties_client: PropertiesClient = Depends(get_properties_client),
) -> CalendarFeedResponse:
    await _assert_property_owner(payload.property_id, current_user, properties_client)
    return await calendar_feed_crud.create(payload.property_id, payload.channel, payload.url)


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_feed(
    request: Request,
    feed_id: UUID,
    current_user: CurrentUser = Depends(_require_manage_or_admin),
    properties_client: PropertiesClient = Depends(get_properties_client),
) -> None:
    feed = await calendar_feed_crud.get(feed_id)
    if feed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    await _assert_property_owner(feed.property_id, current_user, properties_client)
    await calendar_feed_crud.delete(feed_id)


@router.post("/{feed_id}/sync-now", response_model=CalendarFeedResponse)
@limiter.limit("10/minute")
async def sync_feed_now(
    request: Request,
    feed_id: UUID,
    current_user: CurrentUser = Depends(_require_manage_or_admin),
    properties_client: PropertiesClient = Depends(get_properties_client),
) -> CalendarFeedResponse:
    feed = await calendar_feed_crud.get(feed_id)
    if feed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    await _assert_property_owner(feed.property_id, current_user, properties_client)
    logger.info("Manual sync requested for feed {} by {}", feed_id, current_user.id)
    await sync_feed(feed)
    refreshed = await calendar_feed_crud.get(feed_id)
    return CalendarFeedResponse.model_validate(refreshed, from_attributes=True)

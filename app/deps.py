from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import quote, unquote
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from loguru import logger

from app import settings
from app.scopes import BOOKING_SCOPE_DESCRIPTIONS, BookingScope

# ---------------------------------------------------------------------------
# PaymentsClient — thin async wrapper around payments-ms internal API
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.users_ms_url}/auth/token",
    scopes={
        "properties:read": "Browse and search public property listings.",
        **BOOKING_SCOPE_DESCRIPTIONS,
    },
)


@dataclass
class CurrentUser:
    id: UUID
    username: str
    scopes: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return "admin:scopes" in self.scopes


def get_current_user(
    x_user_id: str = Header(...),
    x_username: str = Header(...),
    x_user_scopes: str = Header(default=""),
) -> CurrentUser:
    """
    Reads the headers injected by Traefik after forwardAuth validation.
    The JWT has already been verified — we just trust these headers.
    NOTE: This only works behind Traefik. Run with that assumption.
    """
    try:
        user_id = UUID(x_user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity from gateway",
        ) from None

    scopes = x_user_scopes.split(" ") if x_user_scopes else []

    return CurrentUser(id=user_id, username=unquote(x_username), scopes=scopes)


def require_scopes(*required: str):
    """
    Factory that returns a dependency enforcing one or more scopes.

    Usage:
        @router.get("/protected")
        async def route(user = Depends(require_scopes("bookings:read"))):
            ...
    """

    async def _dep(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        missing = [s for s in required if s not in current_user.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {', '.join(missing)}",
            )
        return current_user

    return _dep


async def require_admin(
    current_user: CurrentUser = Depends(require_scopes("admin:scopes")),
) -> CurrentUser:
    """Shorthand for admin-only endpoints."""
    return current_user


# ---------------------------------------------------------------------------
# Pre-built scope dependencies
# ---------------------------------------------------------------------------

can_read_booking = require_scopes(BookingScope.READ)
can_write_booking = require_scopes(BookingScope.WRITE)
can_cancel_booking = require_scopes(BookingScope.CANCEL)
can_manage_booking = require_scopes(BookingScope.MANAGE)
can_admin_delete_booking = require_scopes(BookingScope.ADMIN_DELETE)


async def can_read_or_manage_booking(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Passes if the user can read bookings (customer/admin) OR manage bookings (owner).
    - bookings:read   → customer sees own bookings
    - bookings:manage → property owner sees bookings for their properties
    - admin:bookings* → admin sees all
    """
    has_read = BookingScope.READ in current_user.scopes
    has_manage = BookingScope.MANAGE in current_user.scopes
    has_admin = (
        BookingScope.ADMIN in current_user.scopes
        or BookingScope.ADMIN_READ in current_user.scopes
    )
    if not (has_read or has_manage or has_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Requires '{BookingScope.READ}' (customers), "
                f"'{BookingScope.MANAGE}' (property owners), "
                f"or '{BookingScope.ADMIN_READ}' (admin)."
            ),
        )
    return current_user


# ---------------------------------------------------------------------------
# PropertiesClient — thin async wrapper around properties-ms internal API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_properties_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.properties_ms_url,
        timeout=httpx.Timeout(5.0),
        follow_redirects=True,
    )


class PropertiesClient:
    """
    Thin async wrapper around the properties-ms internal API.
    Forwards Traefik-injected user headers so properties-ms auth deps work normally.
    """

    @property
    def _client(self) -> httpx.AsyncClient:
        return _get_properties_http_client()

    def _headers(self, user: CurrentUser) -> dict[str, str]:
        return {
            "X-User-Id": str(user.id),
            "X-Username": quote(user.username),
            "X-User-Scopes": " ".join(user.scopes),
        }

    async def get_property(self, property_id: UUID, user: CurrentUser) -> dict | None:
        """Returns property dict or None if 404. Raises HTTPException on other errors."""
        resp = await self._client.get(
            f"/properties/{property_id}", headers=self._headers(user)
        )
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"properties-ms returned {resp.status_code}",
            )
        return resp.json()

    async def get_unavailabilities(
        self, property_id: UUID, user: CurrentUser
    ) -> list[dict]:
        """Returns list of unavailability windows for the property."""
        resp = await self._client.get(
            f"/properties/{property_id}/unavailabilities", headers=self._headers(user)
        )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"properties-ms returned {resp.status_code} for unavailabilities",
            )
        return resp.json()

    async def get_by_ids(self, property_ids: set[UUID], user: CurrentUser) -> list[dict]:
        """Bulk-fetch property list items by ID for name enrichment. Fails silently."""
        if not property_ids:
            return []
        try:
            params = [("ids", str(vid)) for vid in property_ids]
            resp = await self._client.get(
                "/properties/bulk", params=params, headers=self._headers(user)
            )
            if resp.status_code >= 400 or not resp.content:
                return []
            return resp.json()
        except (httpx.RequestError, ValueError):
            return []


_properties_client = PropertiesClient()


def get_properties_client() -> PropertiesClient:
    return _properties_client


# ---------------------------------------------------------------------------
# UsersClient — thin async wrapper around users-ms internal API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_users_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.users_ms_url,
        timeout=httpx.Timeout(5.0),
        follow_redirects=True,
    )


class UsersClient:
    """
    Thin async wrapper around the users-ms internal API.
    Forwards Traefik-injected user headers so users-ms auth deps work normally.
    """

    @property
    def _client(self) -> httpx.AsyncClient:
        return _get_users_http_client()

    def _headers(self, user: CurrentUser) -> dict[str, str]:
        return {
            "X-User-Id": str(user.id),
            "X-Username": quote(user.username),
            "X-User-Scopes": " ".join(user.scopes),
        }

    async def get_by_ids(self, user_ids: set[UUID], user: CurrentUser) -> list[dict]:
        """Bulk-fetch users by ID for name enrichment. Fails silently."""
        if not user_ids:
            return []
        try:
            params = [("ids", str(uid)) for uid in user_ids]
            resp = await self._client.get(
                "/users/bulk", params=params, headers=self._headers(user)
            )
            if resp.status_code >= 400 or not resp.content:
                return []
            return resp.json()
        except (httpx.RequestError, ValueError):
            return []


_users_client = UsersClient()


def get_users_client() -> UsersClient:
    return _users_client


# ---------------------------------------------------------------------------
# PaymentsClient — thin async wrapper around payments-ms internal API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_payments_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.payments_ms_url,
        timeout=httpx.Timeout(5.0),
        follow_redirects=True,
    )


class PaymentsClient:
    """
    Thin async wrapper around payments-ms internal API.
    Called by bookings-ms when a property owner cancels a booking so that
    payments-ms can issue the corresponding Stripe refund.
    Forwards the caller's headers so payments-ms auth works normally.
    Failures are swallowed — refund failure must not block the cancellation.
    """

    @property
    def _client(self) -> httpx.AsyncClient:
        return _get_payments_http_client()

    def _headers(self, user: CurrentUser) -> dict[str, str]:
        return {
            "X-User-Id": str(user.id),
            "X-Username": quote(user.username),
            "X-User-Scopes": " ".join(user.scopes),
        }

    async def refund_booking(self, booking_id: UUID, caller: CurrentUser) -> bool:
        """
        Request a refund for a booking's payment.
        Returns True on success, False on any error (silently degraded).
        """
        try:
            resp = await self._client.post(
                f"/payments/booking/{booking_id}/refund",
                headers=self._headers(caller),
            )
            return resp.status_code < 400
        except (httpx.RequestError, Exception):
            return False


_payments_client = PaymentsClient()


def get_payments_client() -> PaymentsClient:
    return _payments_client


# ---------------------------------------------------------------------------
# System identity for internal service-to-service calls (notifications)
# ---------------------------------------------------------------------------

_SYSTEM_ADMIN: "CurrentUser | None" = None


def _get_system_admin() -> "CurrentUser":
    global _SYSTEM_ADMIN
    if _SYSTEM_ADMIN is None:
        _SYSTEM_ADMIN = CurrentUser(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            username="bookings-ms",
            scopes=["admin:scopes", "admin:notifications:write"],
        )
    return _SYSTEM_ADMIN


# ---------------------------------------------------------------------------
# NotificationsClient — fire-and-forget email dispatch to notifications-ms
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_notifications_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.notifications_ms_url,
        timeout=httpx.Timeout(5.0, read=60.0),
        follow_redirects=True,
    )


class NotificationsClient:
    @property
    def _client(self) -> httpx.AsyncClient:
        return _get_notifications_http_client()

    def _headers(self) -> dict[str, str]:
        admin = _get_system_admin()
        return {
            "X-User-Id": str(admin.id),
            "X-Username": quote(admin.username),
            "X-User-Scopes": " ".join(admin.scopes),
        }

    async def send(
        self, *, to: str, notification_type: str, data: dict | None = None, locale: str | None = None
    ) -> None:
        try:
            logger.debug("Sending notification from bookings-ms | type={} to={} data={}", notification_type, to, data)
            resp = await self._client.post(
                "/notifications/dispatch",
                json={
                    "notification_type": notification_type,
                    "to": to,
                    "data": data or {},
                    "triggered_by": "bookings-ms",
                    "locale": locale,
                },
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                logger.error(
                    "Notification dispatch rejected | type={} to={} status={} body={}",
                    notification_type, to, resp.status_code, resp.text[:500],
                )
            else:
                logger.debug("Successfully sent notification from bookings-ms | type={} to={}", notification_type, to)
        except Exception as exc:
            logger.opt(exception=True).error(
                "Failed to send notification from bookings-ms | type={} to={} error={!r}",
                notification_type, to, exc,
            )


_notifications_client = NotificationsClient()


def get_notifications_client() -> NotificationsClient:
    return _notifications_client

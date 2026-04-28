from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class BookingCreate(BaseModel):
    property_id: UUID
    start_date: date
    end_date: date
    num_guests: int = Field(default=1, ge=1)
    guest_name: str | None = Field(default=None, max_length=255)
    guest_email: str | None = Field(default=None, max_length=255)
    guest_phone: str | None = Field(default=None, max_length=50)
    guest_country: str | None = Field(default=None, max_length=2)
    special_requests: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_date_range(self) -> BookingCreate:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        nights = (self.end_date - self.start_date).days
        if nights < 1:
            raise ValueError("Booking must be at least 1 night")
        return self


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BookingResponse(BaseModel):
    id: UUID
    property_id: UUID
    property_owner_id: UUID
    user_id: UUID
    start_date: date
    end_date: date
    status: BookingStatus
    price_per_night: Decimal
    total_price: Decimal
    currency: str
    num_guests: int
    guest_name: str | None
    guest_email: str | None
    guest_phone: str | None
    guest_country: str | None
    special_requests: str | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingSlot(BaseModel):
    """Minimal occupied slot — reveals no user identity."""

    start_date: date
    end_date: date

    model_config = ConfigDict(from_attributes=True)


class BookingEnriched(BookingResponse):
    """BookingResponse extended with human-readable names from upstream services."""

    property_name: str | None = None
    customer_username: str | None = None
    customer_full_name: str | None = None
    owner_username: str | None = None
    owner_full_name: str | None = None


class BookingFilters(BaseModel):
    """Bind to a FastAPI route via Depends(BookingFilters)."""

    property_id: UUID | None = None
    status: BookingStatus | None = None

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

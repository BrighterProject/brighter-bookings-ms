from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails
from pydantic_core import ValidationError as CoreValidationError

from app.egn import extract_dob_and_gender, is_valid_egn_checksum
from app.models import DocumentType, Gender

# Never let a validation error echo raw government-ID values back to a caller.
# pydantic attaches the offending `input` to every error — for a model-level
# (cross-field) error that `input` is the *whole* payload dict, so masking by
# `loc` alone is insufficient; we mask the sensitive keys wherever they appear.
SENSITIVE_IDENTITY_FIELDS: frozenset[str] = frozenset({"document_number", "pin_egn"})


def _mask_input(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if key in SENSITIVE_IDENTITY_FIELDS else val)
            for key, val in value.items()
        }
    return value


def _sanitize_identity_validation_error(exc: ValidationError) -> CoreValidationError:
    """Rebuild a ValidationError with all sensitive identity values stripped."""
    line_errors: list[InitErrorDetails] = []
    for err in exc.errors():
        loc = err["loc"]
        if loc and any(str(part) in SENSITIVE_IDENTITY_FIELDS for part in loc):
            masked_input: Any = "***"
        else:
            masked_input = _mask_input(err.get("input"))
        line_errors.append(
            InitErrorDetails(
                type="value_error",
                loc=loc,
                input=masked_input,
                ctx={"error": ValueError(err["msg"])},
            )
        )
    return CoreValidationError.from_exception_data(exc.title, line_errors)


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
    payment_method: str | None = None  # card | bank_transfer | cash
    locale: str | None = None

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
    gap_adjustment_pct: Decimal = Decimal("0")
    payment_method: str | None = None
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
    cancellation_policy: str | None = None
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


class GuestIdentityCreate(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    date_of_birth: date
    gender: Gender
    citizenship: str = Field(min_length=2, max_length=2)
    document_type: DocumentType
    document_number: str = Field(min_length=5, max_length=20)
    document_issuing_country: str = Field(min_length=2, max_length=2)
    pin_egn: str | None = Field(default=None, min_length=10, max_length=10)

    model_config = ConfigDict(str_strip_whitespace=True)

    def __init__(self, **data: Any) -> None:
        # Re-raise any validation failure with sensitive values stripped. Done
        # here (outside the validator chain) so pydantic-core doesn't re-wrap and
        # restore the raw `input`. Covers direct construction; the HTTP path is
        # additionally guarded by the sanitizing RequestValidationError handler.
        try:
            super().__init__(**data)
        except ValidationError as exc:
            raise _sanitize_identity_validation_error(exc) from None

    @model_validator(mode="after")
    def validate_bg_requirements_and_egn(self) -> GuestIdentityCreate:
        if self.citizenship == "BG":
            if not self.middle_name or len(self.middle_name.strip()) < 2:
                raise ValueError("middle_name is required for Bulgarian citizens")
            if not self.pin_egn:
                raise ValueError("pin_egn is required for Bulgarian citizens")
        if self.pin_egn:
            if not is_valid_egn_checksum(self.pin_egn):
                raise ValueError("Invalid EGN checksum or format")
            egn_dob, egn_gender = extract_dob_and_gender(self.pin_egn)
            if egn_dob != self.date_of_birth:
                raise ValueError("date_of_birth does not match the birth date encoded in pin_egn")
            if egn_gender != self.gender:
                raise ValueError("gender does not match the gender encoded in pin_egn")
        return self

    def __repr__(self) -> str:
        return (
            f"GuestIdentityCreate(first_name={self.first_name!r}, "
            f"last_name={self.last_name!r}, document_number='***', pin_egn='***')"
        )


class GuestIdentityResponse(BaseModel):
    id: UUID
    booking_id: UUID
    first_name: str
    middle_name: str | None
    last_name: str
    date_of_birth: date | None
    gender: Gender | None
    citizenship: str | None
    document_type: DocumentType | None
    document_number: str | None
    document_issuing_country: str | None
    pin_egn: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    def __repr__(self) -> str:
        return (
            f"GuestIdentityResponse(id={self.id!r}, first_name={self.first_name!r}, "
            f"last_name={self.last_name!r}, document_number='***', pin_egn='***')"
        )


class GuestRosterSlot(BaseModel):
    """Public, unauthenticated roster entry — names only, never document data."""

    filled: bool
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    guest_id: UUID | None = None  # present only when filled=True; used for DELETE


class GuestRosterResponse(BaseModel):
    property_name: str
    property_city: str
    start_date: date
    end_date: date
    total_slots: int
    filled_slots: int
    roster: list[GuestRosterSlot]


class CheckinLinkResponse(BaseModel):
    token: str
    expires_at: date

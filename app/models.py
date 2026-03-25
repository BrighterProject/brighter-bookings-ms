from enum import StrEnum

from ms_core import AbstractModel as Model
from tortoise import fields


class BookingStatus(StrEnum):
    PENDING = "pending"  # just created, awaiting property owner confirmation
    CONFIRMED = "confirmed"  # property owner accepted
    COMPLETED = "completed"  # booking period elapsed, marked done
    CANCELLED = "cancelled"  # cancelled by customer or admin
    NO_SHOW = "no_show"  # customer didn't show up


class Booking(Model):
    id = fields.UUIDField(primary_key=True)

    property_id = fields.UUIDField()
    property_owner_id = fields.UUIDField()  # denormalized snapshot from properties-ms
    user_id = fields.UUIDField()  # the customer who made the booking

    start_datetime = fields.DatetimeField()
    end_datetime = fields.DatetimeField()

    status = fields.CharEnumField(BookingStatus, default=BookingStatus.PENDING)

    price_per_night = fields.DecimalField(
        max_digits=8, decimal_places=2
    )  # snapshot at booking time
    total_price = fields.DecimalField(max_digits=10, decimal_places=2)  # computed
    currency = fields.CharField(max_length=3, default="EUR")

    notes = fields.TextField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:  # type: ignore
        table = "bookings"
        ordering = ["-created_at"]

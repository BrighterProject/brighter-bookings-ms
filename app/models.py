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

    start_date = fields.DateField()
    end_date = fields.DateField()

    status = fields.CharEnumField(BookingStatus, default=BookingStatus.PENDING)

    price_per_night = fields.DecimalField(
        max_digits=8, decimal_places=2
    )  # snapshot at booking time
    total_price = fields.DecimalField(max_digits=10, decimal_places=2)  # computed
    currency = fields.CharField(max_length=3, default="EUR")

    num_guests = fields.IntField(default=1)

    guest_name = fields.CharField(max_length=255, null=True)
    guest_email = fields.CharField(max_length=255, null=True)
    guest_phone = fields.CharField(max_length=50, null=True)
    guest_country = fields.CharField(max_length=2, null=True)  # ISO 3166-1 alpha-2
    special_requests = fields.TextField(null=True)
    gap_adjustment_pct = fields.DecimalField(max_digits=5, decimal_places=2, default=0)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:  # type: ignore
        table = "bookings"
        ordering = ["-created_at"]

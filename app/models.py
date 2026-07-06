from enum import StrEnum

from ms_core import AbstractModel as Model
from tortoise import fields

from app.fields import EncryptedCharField


class BookingStatus(StrEnum):
    PENDING = "pending"  # just created, awaiting property owner confirmation
    CONFIRMED = "confirmed"  # property owner accepted
    COMPLETED = "completed"  # booking period elapsed, marked done
    CANCELLED = "cancelled"  # cancelled by customer or admin
    NO_SHOW = "no_show"  # customer didn't show up


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class DocumentType(StrEnum):
    ID_CARD = "id_card"
    PASSPORT = "passport"


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
    payment_method = fields.CharField(max_length=20, null=True)  # card | bank_transfer | cash
    checkin_link_sent_at = fields.DatetimeField(null=True)  # idempotency marker: dispatch job
    guest_data_purged_at = fields.DatetimeField(null=True)  # idempotency marker: purge job
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "bookings"
        ordering = ["-created_at"]


class GuestIdentity(Model):
    id = fields.UUIDField(primary_key=True)

    booking = fields.ForeignKeyField(
        "models.Booking", related_name="guest_identities", on_delete=fields.CASCADE
    )

    first_name = fields.CharField(max_length=100)
    middle_name = fields.CharField(max_length=100, null=True)
    last_name = fields.CharField(max_length=100)

    # All fields below are required at submission (enforced by GuestIdentityCreate
    # in schemas.py) but nullable at the DB level so the purge job can null them
    # out after the ESTI reporting window — only names survive a purge.
    date_of_birth = fields.DateField(null=True)
    gender = fields.CharEnumField(Gender, null=True)
    citizenship = fields.CharField(max_length=2, null=True)  # ISO 3166-1 alpha-2

    document_type = fields.CharEnumField(DocumentType, null=True)
    document_number = EncryptedCharField(max_length=512, null=True)
    document_issuing_country = fields.CharField(max_length=2, null=True)  # ISO alpha-2
    pin_egn = EncryptedCharField(max_length=512, null=True)  # BG nationals only

    class Meta:
        table = "guest_identities"
        ordering = ["created_at"]

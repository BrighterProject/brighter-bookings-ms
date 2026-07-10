from datetime import date

import pytest
from tortoise import Tortoise

from app.models import Booking, DocumentType, Gender, GuestIdentity

from .factories import CUSTOMER_ID, END_DATE, PROPERTY_ID, PROPERTY_OWNER_ID, START_DATE


@pytest.fixture(autouse=True)
async def _init_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def test_guest_identity_round_trips_encrypted_fields():
    booking = await Booking.create(
        property_id=PROPERTY_ID,
        property_owner_id=PROPERTY_OWNER_ID,
        user_id=CUSTOMER_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        price_per_night="50.00",
        total_price="100.00",
    )
    guest = await GuestIdentity.create(
        booking=booking,
        first_name="Ivan",
        middle_name="Petrov",
        last_name="Ivanov",
        date_of_birth=date(1980, 1, 1),
        gender=Gender.MALE,
        citizenship="BG",
        document_type=DocumentType.ID_CARD,
        document_number="123456789",
        document_issuing_country="BG",
        pin_egn="8001010034",
    )
    fetched = await GuestIdentity.get(id=guest.id)
    assert fetched.document_number == "123456789"
    assert fetched.pin_egn == "8001010034"
    assert fetched.middle_name == "Petrov"


async def test_middle_name_and_pin_egn_are_optional():
    booking = await Booking.create(
        property_id=PROPERTY_ID,
        property_owner_id=PROPERTY_OWNER_ID,
        user_id=CUSTOMER_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        price_per_night="50.00",
        total_price="100.00",
    )
    guest = await GuestIdentity.create(
        booking=booking,
        first_name="John",
        last_name="Smith",
        date_of_birth=date(1990, 5, 5),
        gender=Gender.MALE,
        citizenship="GB",
        document_type=DocumentType.PASSPORT,
        document_number="P1234567",
        document_issuing_country="GB",
    )
    fetched = await GuestIdentity.get(id=guest.id)
    assert fetched.middle_name is None
    assert fetched.pin_egn is None


async def test_booking_has_checkin_tracking_fields_defaulting_to_none():
    booking = await Booking.create(
        property_id=PROPERTY_ID,
        property_owner_id=PROPERTY_OWNER_ID,
        user_id=CUSTOMER_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        price_per_night="50.00",
        total_price="100.00",
    )
    assert booking.checkin_link_sent_at is None
    assert booking.guest_data_purged_at is None

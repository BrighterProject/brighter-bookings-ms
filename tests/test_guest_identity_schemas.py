from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import GuestIdentityCreate


def _payload(**overrides):
    base = dict(
        first_name="Ivan",
        middle_name="Petrov",
        last_name="Ivanov",
        date_of_birth=date(1980, 1, 1),
        gender="male",
        citizenship="BG",
        document_type="id_card",
        document_number="123456789",
        document_issuing_country="BG",
        pin_egn="8001010008",  # valid EGN, dob 1980-01-01, encodes MALE
    )
    return {**base, **overrides}


def test_valid_bg_payload_passes():
    GuestIdentityCreate(**_payload())


def test_non_bg_citizen_with_foreign_document_requires_no_middle_name_or_egn():
    GuestIdentityCreate(
        **_payload(
            citizenship="GB",
            document_type="passport",
            document_issuing_country="GB",
            middle_name=None,
            pin_egn=None,
            gender="male",
        )
    )


def test_bg_issued_document_requires_pin_egn_regardless_of_citizenship():
    # Foreign citizen presenting a Bulgarian-issued document must supply a
    # personal number even though middle_name is not required for them.
    with pytest.raises(ValidationError, match="pin_egn is required"):
        GuestIdentityCreate(
            **_payload(
                citizenship="RU",
                document_issuing_country="BG",
                middle_name=None,
                pin_egn=None,
            )
        )


def test_foreigner_with_bg_document_and_valid_lnch_passes():
    # LNCh encodes no DOB/gender, so no cross-check applies — a foreign citizen
    # with a Bulgarian-issued document and a valid LNCh is accepted.
    GuestIdentityCreate(
        **_payload(
            citizenship="RU",
            document_issuing_country="BG",
            document_type="id_card",
            middle_name=None,
            pin_egn="1000000001",
            date_of_birth=date(1975, 3, 20),
            gender="female",
        )
    )


def test_bg_citizen_without_middle_name_fails():
    with pytest.raises(ValidationError, match="middle_name is required"):
        GuestIdentityCreate(**_payload(middle_name=None))


def test_bg_citizen_without_pin_egn_fails():
    with pytest.raises(ValidationError, match="pin_egn is required"):
        GuestIdentityCreate(**_payload(pin_egn=None))


def test_invalid_egn_and_lnch_checksum_fails():
    # 8001010035 satisfies neither the EGN nor the LNCh checksum.
    with pytest.raises(ValidationError, match="Invalid EGN/LNCh checksum"):
        GuestIdentityCreate(**_payload(pin_egn="8001010035"))


def test_egn_dob_mismatch_fails():
    with pytest.raises(ValidationError, match="date_of_birth does not match"):
        GuestIdentityCreate(**_payload(date_of_birth=date(1999, 9, 9)))


def test_egn_gender_mismatch_fails():
    # 8001010008 encodes MALE — submitting FEMALE must hard-fail.
    with pytest.raises(ValidationError, match="gender does not match"):
        GuestIdentityCreate(**_payload(gender="female"))


def test_validation_error_never_echoes_pin_egn_or_document_number():
    try:
        GuestIdentityCreate(**_payload(pin_egn="8001010035"))
        pytest.fail("expected ValidationError")
    except ValidationError as exc:
        errors_repr = str(exc.errors())
        assert "8001010035" not in errors_repr
        assert "123456789" not in errors_repr

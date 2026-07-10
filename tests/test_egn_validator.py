from datetime import date

import pytest

from app.egn import (
    extract_dob_and_gender,
    is_valid_egn_checksum,
    is_valid_lnch_checksum,
)
from app.models import Gender


@pytest.mark.parametrize(
    "egn,expected_dob,expected_gender",
    [
        # 9th digit parity: even -> MALE, odd -> FEMALE.
        ("8001010034", date(1980, 1, 1), Gender.FEMALE),  # 9th digit '3' odd
        ("9506150023", date(1995, 6, 15), Gender.MALE),  # 9th digit '2' even
        ("0543100119", date(2005, 3, 10), Gender.FEMALE),  # 2000s offset, '1' odd
        ("9031220040", date(1890, 11, 22), Gender.MALE),  # 1800s offset, '4' even, rem=10 edge
    ],
)
def test_valid_egns_pass_checksum_and_extract_correctly(egn, expected_dob, expected_gender):
    assert is_valid_egn_checksum(egn) is True
    dob, gender = extract_dob_and_gender(egn)
    assert dob == expected_dob
    assert gender == expected_gender


def test_wrong_checksum_fails():
    assert is_valid_egn_checksum("8001010035") is False  # last digit changed 4->5


def test_wrong_length_fails():
    assert is_valid_egn_checksum("800101003") is False


def test_non_digit_fails():
    assert is_valid_egn_checksum("800101003A") is False


def test_checksum_valid_but_extracted_gender_can_contradict_submission():
    # 8001010034's checksum is valid and it encodes FEMALE (9th digit '3' is odd).
    # A submission claiming MALE must be caught by the schema-level cross-check;
    # this test only proves extraction is correct.
    assert is_valid_egn_checksum("8001010034") is True
    _, gender = extract_dob_and_gender("8001010034")
    assert gender == Gender.FEMALE


@pytest.mark.parametrize(
    "lnch",
    [
        "1000000001",
        "7452310877",
        "9001123459",
        "6408070009",
        "1234567893",
    ],
)
def test_valid_lnch_passes_checksum(lnch):
    assert is_valid_lnch_checksum(lnch) is True
    # These vectors are LNCh-only — they must not read as valid EGN.
    assert is_valid_egn_checksum(lnch) is False


def test_lnch_wrong_checksum_fails():
    assert is_valid_lnch_checksum("1000000002") is False


@pytest.mark.parametrize("value", ["100000000", "12345678AB", "10000000010"])
def test_lnch_wrong_length_or_non_digit_fails(value):
    assert is_valid_lnch_checksum(value) is False

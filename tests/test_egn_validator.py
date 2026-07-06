from datetime import date

import pytest

from app.egn import extract_dob_and_gender, is_valid_egn_checksum
from app.models import Gender


@pytest.mark.parametrize(
    "egn,expected_dob,expected_gender",
    [
        ("8001010034", date(1980, 1, 1), Gender.MALE),  # 1900s, odd 9th digit
        ("9506150023", date(1995, 6, 15), Gender.FEMALE),  # 1900s, even 9th digit
        ("0543100119", date(2005, 3, 10), Gender.MALE),  # 2000s century offset (+40)
        ("9031220040", date(1890, 11, 22), Gender.FEMALE),  # 1800s offset (+20), rem=10 edge
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
    # 8001010034's checksum is valid and it encodes MALE (9th digit '3' is odd).
    # A submission claiming FEMALE must be caught by the schema-level cross-check;
    # this test only proves extraction is correct.
    assert is_valid_egn_checksum("8001010034") is True
    _, gender = extract_dob_and_gender("8001010034")
    assert gender == Gender.MALE

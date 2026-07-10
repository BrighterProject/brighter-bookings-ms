from __future__ import annotations

from datetime import date

from app.models import Gender

_WEIGHTS = (2, 4, 8, 5, 10, 9, 7, 3, 6)
_LNCH_WEIGHTS = (21, 19, 17, 13, 11, 9, 7, 3, 1)


def is_valid_egn_checksum(egn: str) -> bool:
    if not (len(egn) == 10 and egn.isdigit()):
        return False
    total = sum(int(egn[i]) * _WEIGHTS[i] for i in range(9))
    remainder = total % 11
    check_digit = 0 if remainder == 10 else remainder
    return check_digit == int(egn[9])


def is_valid_lnch_checksum(lnch: str) -> bool:
    """Validate the mod-10 checksum of an LNCh (personal number of a foreigner).

    LNCh is issued by the Bulgarian MVR to foreigners residing long-term in
    Bulgaria. It uses a different weight set and modulus than EGN and encodes
    no birth date/gender. The two registries are independent, so a value may
    satisfy both checksums — callers accept either.
    """
    if not (len(lnch) == 10 and lnch.isdigit()):
        return False
    total = sum(int(lnch[i]) * _LNCH_WEIGHTS[i] for i in range(9))
    return total % 10 == int(lnch[9])


def extract_dob_and_gender(egn: str) -> tuple[date, Gender]:
    """Extract the birth date and gender encoded in a 10-digit EGN.

    Does NOT re-verify the mod-11 checksum — call ``is_valid_egn_checksum``
    first. Raises ValueError if the encoded month/day don't form a real date.
    """
    yy = int(egn[0:2])
    raw_month = int(egn[2:4])
    day = int(egn[4:6])

    if 1 <= raw_month <= 12:
        century_base, month = 1900, raw_month
    elif 21 <= raw_month <= 32:
        century_base, month = 1800, raw_month - 20
    elif 41 <= raw_month <= 52:
        century_base, month = 2000, raw_month - 40
    else:
        raise ValueError(f"EGN has an invalid month digit group: {raw_month:02d}")

    dob = date(century_base + yy, month, day)  # raises ValueError if day/month invalid

    ninth_digit = int(egn[8])
    gender = Gender.MALE if ninth_digit % 2 == 0 else Gender.FEMALE

    return dob, gender

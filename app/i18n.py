"""Locale-aware date formatting for outgoing notification emails.

The notifications service only ships English and Bulgarian email templates, so
any locale other than ``bg`` is normalised to ``en``. ``strftime`` is avoided
because its month names follow the process C locale, not the recipient's.
"""

from __future__ import annotations

from datetime import date
from typing import Final

_MONTHS_FULL: Final[dict[str, tuple[str, ...]]] = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "bg": (
        "януари",
        "февруари",
        "март",
        "април",
        "май",
        "юни",
        "юли",
        "август",
        "септември",
        "октомври",
        "ноември",
        "декември",
    ),
}

_MONTHS_ABBR_EN: Final[tuple[str, ...]] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _normalise(locale: str | None) -> str:
    """Collapse any locale to a supported template locale (``bg`` or ``en``)."""
    return "bg" if (locale or "").lower().startswith("bg") else "en"


def format_date(value: date, locale: str | None = "en") -> str:
    """Format a date as a localised long date (e.g. ``17 June 2026`` / ``17 юни 2026``).

    Args:
        value: The date to format.
        locale: Two-letter locale code; anything but ``bg`` renders English.

    Returns:
        The localised ``day month year`` string.
    """
    months = _MONTHS_FULL[_normalise(locale)]
    return f"{value.day} {months[value.month - 1]} {value.year}"


def format_short_date(value: date, locale: str | None = "en") -> str:
    """Format a date without the year (e.g. ``Jun 17`` / ``17 юни``).

    Args:
        value: The date to format.
        locale: Two-letter locale code; anything but ``bg`` renders English.

    Returns:
        The localised short date string.
    """
    if _normalise(locale) == "bg":
        return f"{value.day} {_MONTHS_FULL['bg'][value.month - 1]}"
    return f"{_MONTHS_ABBR_EN[value.month - 1]} {value.day}"

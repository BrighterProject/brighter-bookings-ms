from datetime import date

from app.i18n import format_date, format_short_date


class TestFormatDate:
    def test_english_long_date(self):
        assert format_date(date(2026, 6, 17), "en") == "17 June 2026"

    def test_bulgarian_long_date(self):
        assert format_date(date(2026, 6, 17), "bg") == "17 юни 2026"

    def test_unsupported_locale_falls_back_to_english(self):
        assert format_date(date(2026, 1, 5), "ru") == "5 January 2026"

    def test_none_locale_defaults_to_english(self):
        assert format_date(date(2026, 12, 31), None) == "31 December 2026"

    def test_locale_with_region_suffix_normalises(self):
        assert format_date(date(2026, 3, 1), "bg-BG") == "1 март 2026"


class TestFormatShortDate:
    def test_english_short_date(self):
        assert format_short_date(date(2026, 6, 17), "en") == "Jun 17"

    def test_bulgarian_short_date(self):
        assert format_short_date(date(2026, 6, 17), "bg") == "17 юни"

    def test_unsupported_locale_falls_back_to_english(self):
        assert format_short_date(date(2026, 8, 9), "ru") == "Aug 9"

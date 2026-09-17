"""Unit tests for the value normalization and comparison helpers."""

from main import is_blank, normalize_key, try_parse_number, values_equal


class TestIsBlank:
    def test_none_is_blank(self):
        assert is_blank(None) is True

    def test_nan_is_blank(self):
        assert is_blank(float("nan")) is True

    def test_empty_string_is_blank(self):
        assert is_blank("") is True

    def test_whitespace_only_is_blank(self):
        assert is_blank("   ") is True

    def test_non_blank_string_is_not_blank(self):
        assert is_blank("hello") is False

    def test_zero_is_not_blank(self):
        assert is_blank("0") is False
        assert is_blank(0) is False


class TestTryParseNumber:
    def test_plain_int_string(self):
        assert try_parse_number("100") == 100.0

    def test_thousands_separator(self):
        assert try_parse_number("100,000.00") == 100000.0

    def test_currency_prefix(self):
        assert try_parse_number("$1,234.50") == 1234.5
        assert try_parse_number("€500") == 500.0

    def test_surrounding_whitespace(self):
        assert try_parse_number("  42  ") == 42.0

    def test_non_numeric_text_returns_none(self):
        assert try_parse_number("abc") is None

    def test_none_returns_none(self):
        assert try_parse_number(None) is None

    def test_already_numeric_type(self):
        assert try_parse_number(42) == 42.0
        assert try_parse_number(3.14) == 3.14


class TestNormalizeKey:
    def test_matches_across_equivalent_forms(self):
        assert normalize_key("1") == normalize_key(" 1 ") == normalize_key(1.0)

    def test_blank_values_normalize_to_none(self):
        # None (rather than an empty-string key) so a merge never treats two
        # blank keys as matching each other.
        assert normalize_key("") is None
        assert normalize_key("  ") is None
        assert normalize_key(None) is None

    def test_text_key_trimmed_and_lowercased(self):
        assert normalize_key(" ABC ") == "abc"

    def test_non_whole_numeric_key_preserved(self):
        assert normalize_key("1.5") == "1.5"


class TestValuesEqual:
    def test_both_blank_are_equal(self):
        assert values_equal("", None, 0.01) is True

    def test_one_blank_one_not_are_unequal(self):
        assert values_equal("", "x", 0.01) is False

    def test_numeric_within_tolerance_is_equal(self):
        assert values_equal("99.995", "100.00", 0.01) is True

    def test_numeric_outside_tolerance_is_unequal(self):
        assert values_equal(100, 150, 0.01) is False

    def test_thousands_formatted_number_matches_plain(self):
        assert values_equal("100000", "100,000.00", 0.01) is True

    def test_text_is_case_insensitive(self):
        assert values_equal("Acme Corp", "acme corp", 0.01) is True

    def test_text_is_whitespace_trimmed(self):
        assert values_equal(" Acme Corp ", "Acme Corp", 0.01) is True

    def test_genuinely_different_text_is_unequal(self):
        assert values_equal("shipped on time", "shipped late", 0.01) is False

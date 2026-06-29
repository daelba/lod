"""Unit tests for lod.date_normalizer.DateNormalizer."""

import unittest

from lod.date_normalizer import DateNormalizer


class DateNormalizerTests(unittest.TestCase):
    def test_iso_day(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("2024-05-01"), "2024-05-01")

    def test_compact_date(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("20240501"), "2024-05-01")

    def test_czech_full_date(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("1. 5. 2024"), "2024-05-01")

    def test_czech_month_year(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("5. 2024"), "2024-05")

    def test_year_only(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("2024"), "2024")

    def test_zero_padding(self):
        n = DateNormalizer()
        # Rules pad single-digit day/month only after year-month-day order is
        # already established by the Czech parser.
        self.assertEqual(n.normalize("1. 5. 2024"), "2024-05-01")

    def test_brackets_and_whitespace(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("[  2024-05-01  ]"), "2024-05-01")

    def test_year_with_zero_month_day(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("2024-00-00"), "2024")
        self.assertEqual(n.normalize("2024-05-00"), "2024-05")

    def test_roman_numerals_disabled_by_default(self):
        n = DateNormalizer()
        # "V" should not become "05" when Roman numeral handling is off.
        self.assertEqual(n.normalize("V"), "V")

    def test_roman_numerals_enabled(self):
        n = DateNormalizer(roman_numerals=True)
        self.assertEqual(n.normalize("V"), "05")
        self.assertEqual(n.normalize("XII"), "12")
        self.assertEqual(n.normalize("I"), "01")

    def test_unparseable_input_unchanged(self):
        n = DateNormalizer()
        self.assertEqual(n.normalize("not-a-date"), "not-a-date")


if __name__ == "__main__":
    unittest.main()

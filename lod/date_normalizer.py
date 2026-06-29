"""Date normalization utilities for Wikibase Time values.

The `DateNormalizer` class converts various human-readable date strings
into ISO-like formats understood by `lod.claim_builder` and the Wikibase
batch API (`YYYY-MM-DD`, `YYYY-MM`, or `YYYY`).

Roman numeral handling is kept optional because the legacy global
replacement rules can accidentally transform non-date text (e.g. the
letter "V").
"""

import re
from typing import List, Tuple


class DateNormalizer:
    """Normalize date strings for Wikibase Time values.

    Args:
        roman_numerals: If True, convert Roman numerals I-XII to month
            numbers before applying ISO formatting. Defaults to False to
            avoid accidental mutation of unrelated text.
        language: Optional language hint used for future locale-specific
            parsers (currently unused).
    """

    # Roman numeral replacement rules; applied only when requested.
    ROMAN_RULES: List[Tuple[str, str]] = [
        ("VIII", "08"),
        ("III", "03"),
        ("VII", "07"),
        ("XII", "12"),
        ("II", "02"),
        ("VI", "06"),
        ("XI", "11"),
        ("IV", "04"),
        ("IX", "09"),
        ("V", "05"),
        ("X", "10"),
        ("I", "01"),
    ]

    # Cleanup + structural transformations.
    ISO_RULES: List[Tuple[str, str]] = [
        (r"(\[ *| *\])", ""),
        (r"^ +", ""),
        (r"^([0-9]{4})([0-9]{2})([0-9]{2})$", r"\1-\2-\3"),
        (r"^([0-9]{1,2})\. *([0-9]{1,2})\. *([0-9]{4})$", r"\3-\2-\1"),
        (r"^([0-9]{1,2})\. *([0-9]{4})$", r"\2-\1"),
        (r"^([0-9])-", r"0\1-"),
        (r"-([0-9])-", r"-0\1-"),
        (r"-([0-9])$", r"-0\1"),
        (r"^([0-9]{4})-00-00$", r"\1"),
        (r"^([0-9]{4}-[0-9]{2})-00$", r"\1"),
    ]

    def __init__(self, *, roman_numerals: bool = False, language: str = "cs"):
        self.roman_numerals = roman_numerals
        self.language = language

    def normalize(self, value: str) -> str:
        """Return normalized date string.

        The result is one of:
        - ``YYYY-MM-DD`` (day precision)
        - ``YYYY-MM`` (month precision)
        - ``YYYY`` (year precision)

        If the input cannot be parsed, it is returned unchanged; callers
        should validate the result before sending it to Wikibase.
        """
        value = str(value).strip()

        rules: List[Tuple[str, str]] = []
        if self.roman_numerals:
            rules.extend(self.ROMAN_RULES)
        rules.extend(self.ISO_RULES)

        result = value
        for pattern, repl in rules:
            result = re.sub(pattern, repl, result)
        return result

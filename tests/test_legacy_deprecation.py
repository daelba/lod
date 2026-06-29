"""Tests for legacy helper deprecation in lod.wikibase.

These helpers used to edit pywikibot Claim objects directly. They are now
removed in favour of the batch ``data["claims"]`` API (``add_claim``,
``remove_claim``, ``update_unique_property``).
"""

import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch


class _FakeItemPage:
    def __init__(self, repo, entity_id="Q1"):
        self.repo = repo
        self._id = entity_id

    def getID(self):
        return self._id


class _FakeSite:
    def __init__(self, code, family):
        self.code = code
        self.family = family

    def data_repository(self):
        return "fake-repo"

    def __repr__(self):
        return "<FakeSite>"


class _FakeClaim:
    pass


class _FakeTimestamp:
    pass


class _FakeWbTime:
    @classmethod
    def fromTimestamp(cls, timestamp, precision):
        return cls()


class _FakeWbQuantity:
    def __init__(self, site, amount, unit):
        self.site = site
        self.amount = amount
        self.unit = unit


class _FakeWbMonolingualText:
    def __init__(self, text, language):
        self.text = text
        self.language = language


class _FakeException(Exception):
    pass


def _install_fake_pywikibot():
    """Install a minimal fake pywikibot module so that lod.wikibase can import."""
    if "pywikibot" in sys.modules:
        return

    fake = types.ModuleType("pywikibot")
    fake.ItemPage = _FakeItemPage
    fake.Site = _FakeSite
    fake.Claim = _FakeClaim
    fake.Timestamp = _FakeTimestamp
    fake.WbTime = _FakeWbTime
    fake.WbQuantity = _FakeWbQuantity
    fake.WbMonolingualText = _FakeWbMonolingualText
    fake.page = types.ModuleType("pywikibot.page")
    fake.page.ItemPage = _FakeItemPage
    fake.exceptions = types.ModuleType("pywikibot.exceptions")
    fake.exceptions.Error = _FakeException
    fake.exceptions.OtherPageSaveError = _FakeException
    sys.modules["pywikibot"] = fake


class LegacyDeprecationTests(unittest.TestCase):
    def _reload_wikibase_with_env(self):
        _install_fake_pywikibot()
        with patch.dict(
            os.environ,
            {
                "LOD_WIKIBASE_ENDPOINT_KEY": "wikibase",
                "LOD_WIKIBASE_SITE_CODE": "code",
                "LOD_WIKIBASE_SITE_FAMILY": "family",
                "LOD_WIKIBASE_PROJECT_CODE": "fg",
                "LOD_WIKIBASE_HOST": "database.factgrid.de",
            },
            clear=True,
        ):
            import lod.wikibase as wikibase

            return importlib.reload(wikibase)

    def test_legacy_helpers_raise_deprecation_error(self):
        """All direct pywikibot editing helpers must raise DeprecationError."""
        wikibase = self._reload_wikibase_with_env()

        legacy_helpers = [
            ("add_qualifier", ("claim", "ec", "P1", "value", "summary")),
            ("add_qualifier_q", ("claim", "ec", "P1", "Q2", "summary")),
            ("add_qualifier_str", ("claim", "ec", "P1", "value", "summary")),
            ("add_qualifier_dat", ("claim", "ec", "P1", "2024-01-01", "summary")),
            ("remove_claim_q", ("item", "ec", "P1", "Q2", "summary")),
            ("remove_claim_str", ("item", "ec", "P1", "value", "summary")),
            ("remove_claim_dat", ("item", "ec", "P1", "2024-01-01", "summary")),
            ("remove_qualifier_str", ("claim", "ec", "P1", "value", "summary")),
        ]

        for name, args in legacy_helpers:
            with self.subTest(helper=name):
                helper = getattr(wikibase, name)
                with self.assertRaises(wikibase.DeprecationError):
                    helper(*args)


if __name__ == "__main__":
    unittest.main()

"""Tests for input validation in lod.wikibase helpers."""

import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch


def _install_fake_pywikibot():
    fake_module = types.ModuleType("pywikibot")

    class FakeItemPage:
        def __init__(self, repo, item_id=None):
            self.repo = repo
            self.item_id = item_id

        def getID(self):
            return self.item_id

    class FakeSite:
        def __init__(self, code, family):
            self.code = code
            self.family = family

        def data_repository(self):
            return "fake-repo"

    fake_module.Site = FakeSite
    fake_module.ItemPage = FakeItemPage
    fake_module.page = types.SimpleNamespace(ItemPage=FakeItemPage)
    fake_module.WbTime = type("WbTime", (), {})
    fake_module.WbQuantity = type("WbQuantity", (), {})
    fake_module.WbMonolingualText = type("WbMonolingualText", (), {})
    fake_module.exceptions = types.SimpleNamespace(
        OtherPageSaveError=Exception,
        Error=Exception,
    )

    sys.modules["pywikibot"] = fake_module


def _reload_wikibase():
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


class WikibaseValidationTests(unittest.TestCase):
    def test_checkid_rejects_invalid_property(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.checkID("invalid", "abc")

    def test_string2entity_rejects_invalid_property(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.string2entity("not-a-pid", "Praha")

    def test_label2entity_rejects_invalid_type(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.label2entity("not-a-qid", "Praha")

    def test_add_claim_rejects_invalid_property(self):
        wikibase = _reload_wikibase()
        with patch.object(wikibase, "_ensure_properties", return_value={"P1": "String"}):
            with self.assertRaises(wikibase.ValidationError):
                wikibase.add_claim("create", {"claims": []}, "bad", "value")

    def test_remove_claim_rejects_invalid_property(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.remove_claim("create", {"claims": []}, "bad", "value")

    def test_remove_property_rejects_invalid_property(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.remove_property("create", {"claims": []}, "bad")

    def test_update_unique_property_rejects_invalid_property(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.update_unique_property("create", {"claims": []}, "bad", "value")

    def test_add_claim_loc_rejects_invalid_propitem(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.add_claim_loc("create", {"claims": []}, "Praha", "bad", "P2")

    def test_add_claim_loc_rejects_invalid_propstring(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.add_claim_loc("create", {"claims": []}, "Praha", "P1", "bad")

    def test_get_statement_id_rejects_invalid_property(self):
        wikibase = _reload_wikibase()
        with self.assertRaises(wikibase.ValidationError):
            wikibase.get_statement_id("create", "bad", "value")

    def test_valid_property_ids_are_accepted(self):
        wikibase = _reload_wikibase()
        item = types.SimpleNamespace(claims={})
        data = {"claims": []}
        # Should not raise; value is empty so no claim is added.
        result = wikibase.add_claim("create", data, "P1", "")
        self.assertEqual(result, data)


if __name__ == "__main__":
    unittest.main()

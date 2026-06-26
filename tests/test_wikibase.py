import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch


class FakeClaim:
    """Minimal fake pywikibot Claim for unique-property tests."""

    def __init__(self, target, snak=None, qualifiers=None, rank="normal"):
        self.target = target
        self.snak = snak or "snak-id"
        self.qualifiers = qualifiers or {}
        self.rank = rank

    def getTarget(self):
        return self.target


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


class WikibaseTests(unittest.TestCase):
    def test_import_lod_without_wikibase_config(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, {}, clear=True):
            import lod

            self.assertTrue(hasattr(lod, "sparql"))

    def test_get_claim_value_returns_string_target(self):
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

            wikibase = importlib.reload(wikibase)
            claim = FakeClaim("expected value")
            self.assertEqual(wikibase._get_claim_value(claim), "expected value")

    def test_update_unique_property_adds_when_no_existing_statements(self):
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

            wikibase = importlib.reload(wikibase)

            item = types.SimpleNamespace(claims={})
            data = {"claims": []}

            with patch.object(wikibase, "remove_property") as mock_remove, patch.object(
                wikibase, "add_claim", return_value={"claims": ["added"]}
            ) as mock_add:
                result = wikibase.update_unique_property(item, data, "P1", "value")

            mock_remove.assert_not_called()
            mock_add.assert_called_once_with(item, data, "P1", "value", quals=None, rank="normal", unit=None)
            self.assertEqual(result, {"claims": ["added"]})

    def test_update_unique_property_skips_when_single_matching_statement(self):
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

            wikibase = importlib.reload(wikibase)

            item = types.SimpleNamespace(claims={"P1": [FakeClaim("value")]})
            data = {"claims": []}

            with patch.object(wikibase, "remove_property") as mock_remove, patch.object(
                wikibase, "add_claim"
            ) as mock_add:
                result = wikibase.update_unique_property(item, data, "P1", "value")

            mock_remove.assert_not_called()
            mock_add.assert_not_called()
            self.assertEqual(result, data)

    def test_update_unique_property_replaces_when_single_different_statement(self):
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

            wikibase = importlib.reload(wikibase)

            item = types.SimpleNamespace(claims={"P1": [FakeClaim("old")]})
            data = {"claims": []}

            def fake_remove(item_arg, data_arg, prop):
                data_arg["claims"].append({"id": "old-snak", "remove": ""})
                return data_arg

            def fake_add(item_arg, data_arg, prop, value, quals=None, rank="normal", unit=None):
                data_arg["claims"].append({"prop": prop, "value": value})
                return data_arg

            with patch.object(wikibase, "remove_property", side_effect=fake_remove) as mock_remove, patch.object(
                wikibase, "add_claim", side_effect=fake_add
            ) as mock_add:
                result = wikibase.update_unique_property(item, data, "P1", "value")

            mock_remove.assert_called_once_with(item, data, "P1")
            mock_add.assert_called_once_with(item, data, "P1", "value", quals=None, rank="normal", unit=None)
            self.assertEqual(result["claims"], [
                {"id": "old-snak", "remove": ""},
                {"prop": "P1", "value": "value"},
            ])

    def test_update_unique_property_replaces_multiple_statements(self):
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

            wikibase = importlib.reload(wikibase)

            item = types.SimpleNamespace(claims={"P1": [FakeClaim("old1"), FakeClaim("old2")]})
            data = {"claims": []}

            def fake_remove(item_arg, data_arg, prop):
                data_arg["claims"].extend([
                    {"id": "old1-snak", "remove": ""},
                    {"id": "old2-snak", "remove": ""},
                ])
                return data_arg

            def fake_add(item_arg, data_arg, prop, value, quals=None, rank="normal", unit=None):
                data_arg["claims"].append({"prop": prop, "value": value})
                return data_arg

            with patch.object(wikibase, "remove_property", side_effect=fake_remove) as mock_remove, patch.object(
                wikibase, "add_claim", side_effect=fake_add
            ) as mock_add:
                result = wikibase.update_unique_property(item, data, "P1", "value")

            mock_remove.assert_called_once_with(item, data, "P1")
            mock_add.assert_called_once_with(item, data, "P1", "value", quals=None, rank="normal", unit=None)
            self.assertEqual(len(result["claims"]), 3)

    def _reload_wikibase(self):
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

    def test_get_statement_id_matches_string_target(self):
        wikibase = self._reload_wikibase()
        item = types.SimpleNamespace(claims={"P1": [FakeClaim("hello", snak="s1")]})
        self.assertEqual(wikibase.get_statement_id(item, "P1", "hello"), "s1")

    def test_get_statement_id_returns_none_when_no_match(self):
        wikibase = self._reload_wikibase()
        item = types.SimpleNamespace(claims={"P1": [FakeClaim("hello", snak="s1")]})
        self.assertIsNone(wikibase.get_statement_id(item, "P1", "world"))

    def test_get_statement_id_matches_item_page_target(self):
        wikibase = self._reload_wikibase()
        target = wikibase.pywikibot.ItemPage("repo", "Q42")
        item = types.SimpleNamespace(claims={"P1": [FakeClaim(target, snak="s2")]})
        self.assertEqual(wikibase.get_statement_id(item, "P1", "Q42"), "s2")

    def test_get_statement_id_matches_time_target_by_precision(self):
        wikibase = self._reload_wikibase()
        target = wikibase.pywikibot.WbTime()
        target.year = 2024
        target.month = 6
        target.day = 15
        target.precision = 11
        item = types.SimpleNamespace(claims={"P1": [FakeClaim(target, snak="s3")]})
        self.assertEqual(wikibase.get_statement_id(item, "P1", "2024-06-15"), "s3")
        self.assertIsNone(wikibase.get_statement_id(item, "P1", "2024-06"))

    def test_get_statement_id_matches_quantity_without_unit(self):
        wikibase = self._reload_wikibase()
        target = wikibase.pywikibot.WbQuantity()
        target.amount = "+500"
        target.unit = None
        item = types.SimpleNamespace(claims={"P1": [FakeClaim(target, snak="s4")]})
        self.assertEqual(wikibase.get_statement_id(item, "P1", "500"), "s4")
        self.assertEqual(wikibase.get_statement_id(item, "P1", "+500"), "s4")

    def test_get_statement_id_matches_quantity_with_unit(self):
        wikibase = self._reload_wikibase()
        target = wikibase.pywikibot.WbQuantity()
        target.amount = "+500"
        target.unit = wikibase.pywikibot.ItemPage("repo", "Q11573")
        item = types.SimpleNamespace(claims={"P1": [FakeClaim(target, snak="s5")]})
        self.assertEqual(wikibase.get_statement_id(item, "P1", "500Q11573"), "s5")
        self.assertEqual(wikibase.get_statement_id(item, "P1", "500"), "s5")
        self.assertIsNone(wikibase.get_statement_id(item, "P1", "500Q11574"))

    def test_get_statement_id_respects_rank(self):
        wikibase = self._reload_wikibase()
        item = types.SimpleNamespace(claims={"P1": [FakeClaim("x", snak="s6", rank="preferred")]})
        self.assertEqual(wikibase.get_statement_id(item, "P1", "x", rank="preferred"), "s6")
        self.assertIsNone(wikibase.get_statement_id(item, "P1", "x", rank="normal"))

    def test_get_statement_id_matches_qualifiers(self):
        wikibase = self._reload_wikibase()
        qualifier = FakeClaim("cs")
        item = types.SimpleNamespace(
            claims={"P1": [FakeClaim("hello", snak="s7", qualifiers={"P2": [qualifier]})]}
        )
        self.assertEqual(wikibase.get_statement_id(item, "P1", "hello", quals=[["P2", "cs"]]), "s7")
        self.assertIsNone(wikibase.get_statement_id(item, "P1", "hello", quals=[["P2", "en"]]))

    def test_checkid_uses_project_code_prefixes(self):
        _install_fake_pywikibot()

        with patch.dict(
            os.environ,
            {
                "WIKIBASE_ENDPOINT_KEY": "wikibase",
                "WIKIBASE_SITE_CODE": "code",
                "WIKIBASE_SITE_FAMILY": "family",
                "WIKIBASE_PROJECT_CODE": "fg",
                "WIKIBASE_HOST": "database.factgrid.de",
            },
            clear=True,
        ):
            import lod.wikibase as wikibase

            wikibase = importlib.reload(wikibase)
            captured = {}

            def _fake_get_endpoint(name):
                return "https://example.test/sparql"

            def _fake_sparql(endpoint, query):
                captured["query"] = query
                return {
                    "results": {
                        "bindings": [
                            {"item": {"value": "https://example.test/entity/Q42"}}
                        ]
                    }
                }

            with patch.object(wikibase, "get_endpoint", _fake_get_endpoint), patch.object(
                wikibase, "sparql", _fake_sparql
            ):
                item = wikibase.checkID("P12", "abc")

            self.assertEqual(item.getID(), "Q42")
            self.assertIn("fg_wdt:P12", captured["query"])
            self.assertIn("PREFIX fg_wd: <http://database.factgrid.de/entity/>", captured["query"])


if __name__ == "__main__":
    unittest.main()

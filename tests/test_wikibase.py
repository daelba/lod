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

            item = types.SimpleNamespace(claims={"P1": [FakeClaim("old", snak="old-snak")]})
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
            # add_claim receives a temporary item with the property cleared so
            # the old value is not seen during the existence check.
            self.assertEqual(mock_add.call_count, 1)
            call_args = mock_add.call_args
            self.assertEqual(call_args.args[2:], ("P1", "value"))
            self.assertEqual(call_args.kwargs, {"quals": None, "rank": "normal", "unit": None})
            temp_item = call_args.args[0]
            self.assertEqual(temp_item.claims["P1"], [])
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

            item = types.SimpleNamespace(claims={
                "P1": [
                    FakeClaim("old1", snak="old1-snak"),
                    FakeClaim("old2", snak="old2-snak"),
                ],
            })
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
            self.assertEqual(mock_add.call_count, 1)
            temp_item = mock_add.call_args.args[0]
            self.assertEqual(temp_item.claims["P1"], [])
            self.assertEqual(len(result["claims"]), 3)

    def test_update_unique_property_keeps_one_matching_and_removes_others(self):
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

            item = types.SimpleNamespace(claims={
                "P1": [
                    FakeClaim("value", snak="keep-snak"),
                    FakeClaim("other", snak="remove-snak"),
                ],
            })
            data = {"claims": []}

            with patch.object(wikibase, "remove_property") as mock_remove, patch.object(
                wikibase, "add_claim"
            ) as mock_add:
                result = wikibase.update_unique_property(item, data, "P1", "value")

            mock_remove.assert_not_called()
            mock_add.assert_not_called()
            self.assertEqual(result["claims"], [
                {"id": "remove-snak", "remove": ""},
            ])

    def test_update_unique_property_keeps_one_matching_when_duplicates(self):
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

            item = types.SimpleNamespace(claims={
                "P1": [
                    FakeClaim("value", snak="keep-snak"),
                    FakeClaim("value", snak="dup-snak"),
                    FakeClaim("other", snak="remove-snak"),
                ],
            })
            data = {"claims": []}

            with patch.object(wikibase, "remove_property") as mock_remove, patch.object(
                wikibase, "add_claim"
            ) as mock_add:
                result = wikibase.update_unique_property(item, data, "P1", "value")

            mock_remove.assert_not_called()
            mock_add.assert_not_called()
            self.assertEqual(result["claims"], [
                {"id": "dup-snak", "remove": ""},
                {"id": "remove-snak", "remove": ""},
            ])

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

    def test_normal_dat_delegates_to_date_normalizer(self):
        import lod.wikibase as wikibase

        self.assertEqual(wikibase.normal_dat("1. 5. 2024"), "2024-05-01")
        self.assertEqual(wikibase.normal_dat("V"), "05")  # legacy Roman numeral behavior

    def test_properties_cache_reuses_result(self):
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
            wikibase.properties = None
            wikibase._properties_cache = None
            wikibase._properties_cache_timestamp = 0.0

            call_count = {"n": 0}

            def fake_list_properties(self):
                call_count["n"] += 1
                return {"P1": "String"}

            with patch.object(wikibase.WikibaseClient, "list_properties", fake_list_properties):
                first = wikibase._ensure_properties()
                second = wikibase._ensure_properties()

            self.assertEqual(first, {"P1": "String"})
            self.assertIs(second, first)
            self.assertEqual(call_count["n"], 1)

    def test_refresh_properties_invalidates_cache(self):
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
            wikibase.properties = None
            wikibase._properties_cache = None
            wikibase._properties_cache_timestamp = 0.0

            call_count = {"n": 0}

            def fake_list_properties(self):
                call_count["n"] += 1
                return {"P1": "String", "P2": "Item"}

            with patch.object(wikibase.WikibaseClient, "list_properties", fake_list_properties):
                first = wikibase._ensure_properties()
                wikibase.refresh_properties()
                second = wikibase._ensure_properties()

            self.assertEqual(first, {"P1": "String", "P2": "Item"})
            self.assertEqual(second, {"P1": "String", "P2": "Item"})
            self.assertEqual(call_count["n"], 2)

    def test_prefix_block_is_cached(self):
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
            wikibase._prefix_block_cache = {}

            first = wikibase._wikibase_prefix_block()
            second = wikibase._wikibase_prefix_block()

            self.assertIs(second, first)
            self.assertIn("fg_wd:", first)
            self.assertEqual(len(wikibase._prefix_block_cache), 1)


class AddClaimReferenceTests(unittest.TestCase):
    _ENV = {
        "WIKIBASE_ENDPOINT_KEY": "wikibase",
        "WIKIBASE_SITE_CODE": "code",
        "WIKIBASE_SITE_FAMILY": "family",
        "WIKIBASE_PROJECT_CODE": "fg",
        "WIKIBASE_HOST": "database.factgrid.de",
    }

    def _reload_wikibase(self):
        _install_fake_pywikibot()
        import lod.wikibase as wikibase

        with patch.dict(os.environ, self._ENV, clear=True):
            return importlib.reload(wikibase)

    def test_add_claim_includes_references(self):
        _install_fake_pywikibot()
        import lod.wikibase as wikibase

        with patch.dict(os.environ, self._ENV, clear=True):
            wikibase = importlib.reload(wikibase)
            item = types.SimpleNamespace(claims={})
            data = {"claims": []}

            with patch.object(
                wikibase,
                "_ensure_properties",
                return_value={"P1": "String", "P48": "WikibaseItem", "P854": "Url"},
            ):
                result = wikibase.add_claim(
                    item,
                    data,
                    "P1",
                    "hello",
                    references=[("P48", "Q123"), ("P854", "https://example.org")],
                )

        self.assertEqual(len(result["claims"]), 1)
        claim = result["claims"][0]
        self.assertIn("references", claim)
        snaks = claim["references"][0]["snaks"]
        self.assertEqual(snaks["P48"][0]["datavalue"]["value"]["numeric-id"], "123")
        self.assertEqual(snaks["P854"][0]["datavalue"]["value"], "https://example.org")

    def test_add_claim_with_references_and_qualifiers(self):
        _install_fake_pywikibot()
        import lod.wikibase as wikibase

        with patch.dict(os.environ, self._ENV, clear=True):
            wikibase = importlib.reload(wikibase)
            item = types.SimpleNamespace(claims={})
            data = {"claims": []}

            with patch.object(
                wikibase,
                "_ensure_properties",
                return_value={"P1": "String", "P2": "String", "P48": "WikibaseItem"},
            ):
                result = wikibase.add_claim(
                    item,
                    data,
                    "P1",
                    "hello",
                    quals=[["P2", "qualifier value"]],
                    references=[{"property": "P48", "value": "Q456"}],
                )

        claim = result["claims"][0]
        self.assertEqual(len(claim["qualifiers"]), 1)
        self.assertEqual(claim["qualifiers"][0]["datavalue"]["value"], "qualifier value")
        self.assertEqual(
            claim["references"][0]["snaks"]["P48"][0]["datavalue"]["value"]["numeric-id"],
            "456",
        )


if __name__ == "__main__":
    unittest.main()

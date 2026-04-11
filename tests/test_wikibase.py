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

    def test_checkid_uses_project_code_prefixes(self):
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

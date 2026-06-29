"""Unit tests for lod.wikibase_client.WikibaseClient."""

import os
import sys
import types
import unittest
from unittest.mock import patch


class FakeSite:
    def __init__(self, code, family):
        self.code = code
        self.family = family

    def data_repository(self):
        return "fake-repo"


class FakeItemPage:
    def __init__(self, repo, item_id=None):
        self.repo = repo
        self.item_id = item_id

    def getID(self):
        return self.item_id


def _install_fake_pywikibot():
    fake_module = types.ModuleType("pywikibot")
    fake_module.Site = FakeSite
    fake_module.ItemPage = FakeItemPage
    fake_module.page = types.SimpleNamespace(ItemPage=FakeItemPage)
    fake_module.exceptions = types.SimpleNamespace(
        OtherPageSaveError=Exception,
        Error=Exception,
    )
    sys.modules["pywikibot"] = fake_module


class WikibaseClientTests(unittest.TestCase):
    @staticmethod
    def _client_env():
        return {
            "WIKIBASE_ENDPOINT_KEY": "wikibase",
            "WIKIBASE_SITE_CODE": "code",
            "WIKIBASE_SITE_FAMILY": "family",
            "WIKIBASE_PROJECT_CODE": "fg",
            "WIKIBASE_HOST": "database.factgrid.de",
        }

    def test_client_reads_project_code_and_host(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            self.assertEqual(client.project_code, "fg")
            self.assertEqual(client.host, "database.factgrid.de")

    def test_client_supports_lod_prefixed_env_vars(self):
        _install_fake_pywikibot()
        env = {f"LOD_{k}": v for k, v in self._client_env().items()}
        with patch.dict(os.environ, env, clear=True):
            import lod.wikibase_client as client_module
            from lod.wikibase_client import WikibaseClient

            with patch.object(client_module, "get_endpoint", return_value="fake-endpoint"):
                client = WikibaseClient()
                self.assertEqual(client.project_code, "fg")
                self.assertEqual(client.sparql_endpoint(), "fake-endpoint")

    def test_repo_is_lazy(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            self.assertIsNone(client._repo)
            self.assertEqual(client.repo(), "fake-repo")
            self.assertEqual(client._repo, "fake-repo")

    def test_properties_cache_with_ttl(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            call_count = {"n": 0}

            def fake_list_properties():
                call_count["n"] += 1
                return {"P1": "String"}

            with patch.object(client, "list_properties", side_effect=fake_list_properties):
                first = client.properties()
                second = client.properties()

            self.assertIs(second, first)
            self.assertEqual(call_count["n"], 1)

    def test_refresh_properties_clears_cache(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            call_count = {"n": 0}

            def fake_list_properties():
                call_count["n"] += 1
                return {"P1": "String"}

            with patch.object(client, "list_properties", side_effect=fake_list_properties):
                client.properties()
                client.refresh_properties()
                client.properties()

            self.assertEqual(call_count["n"], 2)

    def test_prefix_block_is_cached(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            first = client.prefix_block()
            second = client.prefix_block()
            self.assertIs(second, first)
            self.assertIn("PREFIX fg_wd:", first)

    def test_label2entity_builds_query_with_prefixes(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            captured = {}

            def fake_sparql(endpoint, query):
                captured["query"] = query
                return {"results": {"bindings": []}}

            with patch.object(client, "sparql_endpoint", return_value="fake-endpoint"), \
                 patch("lod.wikibase_client.sparql", side_effect=fake_sparql):
                client.label2entity(None, "Praha")

            self.assertIn("PREFIX fg_wd:", captured["query"])
            self.assertIn('"Praha"@cs', captured["query"])
            self.assertIn("LIMIT 10", captured["query"])

    def test_string2entity_builds_query_with_prefixes(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            captured = {}

            def fake_sparql(endpoint, query):
                captured["query"] = query
                return {"results": {"bindings": []}}

            with patch.object(client, "sparql_endpoint", return_value="fake-endpoint"), \
                 patch("lod.wikibase_client.sparql", side_effect=fake_sparql):
                client.string2entity("P131", "Praha")

            self.assertIn("PREFIX fg_pq:", captured["query"])
            self.assertIn("fg_pq:P1932", captured["query"])
            self.assertIn("fg_ps:P131", captured["query"])

    def test_normal_dat_defaults_to_roman_numerals(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            self.assertEqual(client.normal_dat("V"), "05")
            self.assertEqual(client.normal_dat("1. 5. 2024"), "2024-05-01")

    def test_normal_dat_can_disable_roman_numerals(self):
        _install_fake_pywikibot()
        with patch.dict(os.environ, self._client_env(), clear=True):
            from lod.wikibase_client import WikibaseClient

            client = WikibaseClient()
            self.assertEqual(client.normal_dat("V", roman_numerals=False), "V")


if __name__ == "__main__":
    unittest.main()

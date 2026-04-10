import unittest
from unittest.mock import patch

from lod import endpoints


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload
        self.headers = self

    def get_content_charset(self):
        return "utf-8"

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None


class EndpointsTests(unittest.TestCase):
    def test_sparql_retries_then_succeeds(self):
        calls = {"count": 0}

        def _flaky_urlopen(request, timeout):
            calls["count"] += 1
            if calls["count"] < 3:
                raise OSError("temporary")
            return _DummyResponse(b'{"results": {"bindings": []}}')

        with patch("lod.endpoints.urlopen", side_effect=_flaky_urlopen):
            result = endpoints.sparql(
                "https://example.test/sparql",
                "SELECT * WHERE { ?s ?p ?o }",
                max_retries=3,
                retry_delay_seconds=0,
            )

        self.assertEqual(result["results"]["bindings"], [])
        self.assertEqual(calls["count"], 3)

    def test_sparql_raises_after_retry_limit(self):
        with patch("lod.endpoints.urlopen", side_effect=OSError("down")):
            with self.assertRaises(RuntimeError):
                endpoints.sparql(
                    "https://example.test/sparql",
                    "SELECT * WHERE { ?s ?p ?o }",
                    max_retries=1,
                    retry_delay_seconds=0,
                )

    def test_get_bigdata_rejects_limit_offset_in_query(self):
        with self.assertRaises(ValueError):
            endpoints.get_bigData(
                "https://example.test/sparql",
                "SELECT * WHERE { ?s ?p ?o } LIMIT 1",
            )


if __name__ == "__main__":
    unittest.main()

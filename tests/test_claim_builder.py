"""Unit tests for lod.claim_builder.ClaimBuilder."""

import unittest

from lod.claim_builder import ClaimBuilder, build_claim_key
from lod.errors import ValidationError


class ClaimBuilderTests(unittest.TestCase):
    def _builder(self, properties=None):
        return ClaimBuilder(properties or {}, "database.factgrid.de")

    def test_build_item(self):
        builder = self._builder({"P1": "WikibaseItem"})
        claim = builder.build_claim("P1", "Q42")

        self.assertEqual(claim["type"], "statement")
        self.assertEqual(claim["rank"], "normal")
        self.assertEqual(claim["mainsnak"]["property"], "P1")
        self.assertEqual(
            claim["mainsnak"]["datavalue"],
            {
                "value": {"entity-type": "item", "numeric-id": "42"},
                "type": "wikibase-entityid",
            },
        )

    def test_build_item_with_prefix(self):
        builder = self._builder({"P1": "WikibaseItem"})
        claim = builder.build_claim("P1", "Q42", rank="preferred")
        self.assertEqual(claim["rank"], "preferred")

    def test_build_item_rejects_invalid_value(self):
        builder = self._builder({"P1": "WikibaseItem"})
        with self.assertRaises(ValidationError):
            builder.build_claim("P1", "not-an-item")

    def test_build_string_types(self):
        builder = self._builder(
            {"P2": "String", "P3": "ExternalId", "P4": "Url", "P5": "url"}
        )
        for prop in ("P2", "P3", "P4", "P5"):
            with self.subTest(prop=prop):
                claim = builder.build_claim(prop, "  hello  ")
                self.assertEqual(
                    claim["mainsnak"]["datavalue"],
                    {"value": "hello", "type": "string"},
                )

    def test_build_monolingualtext(self):
        builder = self._builder({"P6": "Monolingualtext"})
        claim = builder.build_claim("P6", "text")
        self.assertEqual(
            claim["mainsnak"]["datavalue"],
            {
                "value": {"text": "text", "language": "cs"},
                "type": "monolingualtext",
            },
        )

    def test_build_time_day(self):
        builder = self._builder({"P7": "Time"})
        claim = builder.build_claim("P7", "2024-05-01")
        value = claim["mainsnak"]["datavalue"]["value"]
        self.assertEqual(value["time"], "+2024-05-01T00:00:00Z")
        self.assertEqual(value["precision"], 11)

    def test_build_time_month(self):
        builder = self._builder({"P7": "Time"})
        claim = builder.build_claim("P7", "2024-05")
        value = claim["mainsnak"]["datavalue"]["value"]
        self.assertEqual(value["time"], "+2024-05-00T00:00:00Z")
        self.assertEqual(value["precision"], 10)

    def test_build_time_year(self):
        builder = self._builder({"P7": "Time"})
        claim = builder.build_claim("P7", "2024")
        value = claim["mainsnak"]["datavalue"]["value"]
        self.assertEqual(value["time"], "+2024-00-00T00:00:00Z")
        self.assertEqual(value["precision"], 9)

    def test_build_time_invalid_returns_none(self):
        builder = self._builder({"P7": "Time"})
        self.assertIsNone(builder.build_claim("P7", "not-a-date"))

    def test_build_quantity_without_unit(self):
        builder = self._builder({"P8": "Quantity"})
        claim = builder.build_claim("P8", "500")
        value = claim["mainsnak"]["datavalue"]["value"]
        self.assertEqual(value["amount"], "+500")
        self.assertEqual(value["unit"], "1")

    def test_build_quantity_with_unit(self):
        builder = self._builder({"P8": "Quantity"})
        claim = builder.build_claim("P8", "+500", unit="Q11573")
        value = claim["mainsnak"]["datavalue"]["value"]
        self.assertEqual(value["amount"], "+500")
        self.assertEqual(value["unit"], "http://database.factgrid.de/entity/Q11573")

    def test_build_unknown_property_raises(self):
        builder = self._builder()
        with self.assertRaises(ValidationError):
            builder.build_claim("P99", "value")

    def test_build_qualifier(self):
        builder = self._builder({"P9": "WikibaseItem", "P10": "String"})
        q1 = builder.build_qualifier("P9", "Q5")
        q2 = builder.build_qualifier("P10", "hello")

        self.assertNotIn("rank", q1)
        self.assertEqual(q1["datavalue"]["type"], "wikibase-entityid")
        self.assertEqual(q2["datavalue"]["type"], "string")

    def test_build_claim_does_not_add_qualifiers(self):
        # Qualifiers are assembled by the caller (e.g. add_claim), not by
        # ClaimBuilder.build_claim itself.
        builder = self._builder({"P1": "WikibaseItem"})
        claim = builder.build_claim("P1", "Q42")
        self.assertNotIn("qualifiers", claim)


class BuildClaimKeyTests(unittest.TestCase):
    def test_plain_value(self):
        prop, value = build_claim_key("P1", "v", properties_map={"P1": "String"})
        self.assertEqual(prop, "P1")
        self.assertEqual(value, "v")

    def test_quantity_with_unit(self):
        prop, value = build_claim_key(
            "P8", "500", properties_map={"P8": "Quantity"}, unit="Q11573"
        )
        self.assertEqual(value, "500Q11573")

    def test_quantity_without_unit(self):
        prop, value = build_claim_key(
            "P8", "500", properties_map={"P8": "Quantity"}
        )
        self.assertEqual(value, "500")


class ReferenceTests(unittest.TestCase):
    def _builder(self, properties=None):
        return ClaimBuilder(properties or {}, "database.factgrid.de")

    def test_reference_from_tuples(self):
        builder = self._builder({"P1": "WikibaseItem", "P48": "WikibaseItem", "P854": "Url"})
        claim = builder.build_claim(
            "P1", "Q42", references=[("P48", "Q123"), ("P854", "https://example.org")]
        )

        self.assertIn("references", claim)
        self.assertEqual(len(claim["references"]), 1)
        snaks = claim["references"][0]["snaks"]
        self.assertEqual(len(snaks), 2)
        self.assertEqual(snaks["P48"][0]["datavalue"]["type"], "wikibase-entityid")
        self.assertEqual(snaks["P48"][0]["datavalue"]["value"]["numeric-id"], "123")
        self.assertEqual(snaks["P854"][0]["datavalue"]["type"], "string")
        self.assertEqual(snaks["P854"][0]["datavalue"]["value"], "https://example.org")

    def test_reference_from_dicts(self):
        builder = self._builder({"P1": "String", "P248": "WikibaseItem"})
        claim = builder.build_claim(
            "P1", "hello", references=[{"property": "P248", "value": "Q456"}]
        )

        snaks = claim["references"][0]["snaks"]
        self.assertEqual(snaks["P248"][0]["datavalue"]["type"], "wikibase-entityid")
        self.assertEqual(snaks["P248"][0]["datavalue"]["value"]["numeric-id"], "456")

    def test_reference_from_property_dict(self):
        builder = self._builder({"P1": "String", "P143": "WikibaseItem", "P854": "Url"})
        claim = builder.build_claim(
            "P1", "hello", references=[{"P143": "Q1", "P854": "https://x"}]
        )

        snaks = claim["references"][0]["snaks"]
        self.assertEqual(snaks["P143"][0]["datavalue"]["value"]["numeric-id"], "1")
        self.assertEqual(snaks["P854"][0]["datavalue"]["value"], "https://x")

    def test_no_references_when_none(self):
        builder = self._builder({"P1": "String"})
        claim = builder.build_claim("P1", "hello")
        self.assertNotIn("references", claim)

    def test_empty_references_ignored(self):
        builder = self._builder({"P1": "String"})
        claim = builder.build_claim("P1", "hello", references=[])
        self.assertNotIn("references", claim)

    def test_invalid_reference_entry_raises(self):
        builder = self._builder({"P1": "String"})
        with self.assertRaises(ValidationError):
            builder.build_claim("P1", "hello", references=["bad-entry"])


if __name__ == "__main__":
    unittest.main()

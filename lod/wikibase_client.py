"""WikibaseClient – high-level client wrapping pywikibot and SPARQL helpers.

This module provides a stateful, testable client for Wikibase instances. It
replaces the global mutable state in ``lod.wikibase`` (``site``, ``repo``,
``properties``) with lazy cached properties scoped to the client instance.

The module-level helpers in ``lod.wikibase`` remain as a thin compatibility
facade delegating to a default client.
"""

import functools
import logging
import os
import re
import time
from typing import Any, Optional

import pywikibot

from .claim_builder import ClaimBuilder, build_claim_key
from .config_loader import load_config
from .date_normalizer import DateNormalizer
from .endpoints import get_endpoint, sparql
from .errors import ConfigurationError

_logger = logging.getLogger(__name__)


class WikibaseClient:
    """Client for a single Wikibase instance.

    Configuration is read from the provided config object or from the default
    config loader. Environment variables (plain or ``LOD_`` prefixed) take
    precedence over config attributes, matching the behaviour of the legacy
    module-level helpers.
    """

    # TTL for the cached property type map.
    _PROPERTIES_CACHE_TTL_SECONDS = 300

    def __init__(self, config: Optional[Any] = None):
        self._cfg = config or load_config()

        # Instance-level caches. These replace the global ``site``/``repo``/
        # ``properties`` state from the legacy implementation.
        self._site: Optional["pywikibot.Site"] = None
        self._repo: Optional["pywikibot.DataSite"] = None
        self._properties: Optional[dict[str, str]] = None
        self._properties_timestamp: float = 0.0
        self._prefix_block: Optional[str] = None

    # --------------------------------------------------------------------- #
    # Configuration helpers
    # --------------------------------------------------------------------- #
    def _cfg_value(self, name: str, default: Any = None) -> Any:
        """Read a config value from env (plain or LOD_ prefixed) or config."""
        for env_name in (name, f"LOD_{name}"):
            value = os.getenv(env_name)
            if value is not None:
                return value
        if self._cfg:
            return getattr(self._cfg, name, default)
        return default

    def _require_cfg(self, name: str) -> str:
        """Return a required config value or raise ConfigurationError."""
        value = self._cfg_value(name)
        if value:
            return value
        raise ConfigurationError(
            f"Missing {name} (set in lod_config.py or environment variable).",
            name=name,
        )

    @functools.cached_property
    def project_code(self) -> str:
        return self._require_cfg("WIKIBASE_PROJECT_CODE")

    @functools.cached_property
    def host(self) -> str:
        """Host used to build Wikibase RDF namespace IRIs (without protocol)."""
        host = self._require_cfg("WIKIBASE_HOST")
        host = re.sub(r"^https?://", "", host.strip())
        return host.rstrip("/")

    def sparql_endpoint(self) -> str:
        return get_endpoint(self._require_cfg("WIKIBASE_ENDPOINT_KEY"))

    # --------------------------------------------------------------------- #
    # Site / repo helpers
    # --------------------------------------------------------------------- #
    def site(self) -> "pywikibot.Site":
        """Return (and lazily create) the pywikibot Site instance."""
        if self._site is None:
            site_code = self._require_cfg("WIKIBASE_SITE_CODE")
            family = self._require_cfg("WIKIBASE_SITE_FAMILY")
            self._site = pywikibot.Site(site_code, family)
        return self._site

    def repo(self) -> "pywikibot.DataSite":
        """Return (and lazily create) the pywikibot DataSite instance."""
        if self._repo is None:
            self._repo = self.site().data_repository()
        return self._repo

    # --------------------------------------------------------------------- #
    # Property map helpers
    # --------------------------------------------------------------------- #
    def list_properties(self) -> dict[str, str]:
        """Fetch the map of property IDs to their Wikibase datatypes."""
        query = (
            "SELECT * WHERE { ?property a wikibase:Property; "
            "wikibase:propertyType ?datatype. }"
        )
        result = sparql(self.sparql_endpoint(), query)
        props = {}
        for binding in result["results"]["bindings"]:
            prop_id = binding["property"]["value"].split("/")[-1]
            prop_datatype = binding["datatype"]["value"].split("#")[-1]
            props[prop_id] = prop_datatype
        return props

    def properties(self) -> dict[str, str]:
        """Return the cached property type map, refreshing if TTL expired."""
        if self._properties is not None:
            age = time.monotonic() - self._properties_timestamp
            if age < self._PROPERTIES_CACHE_TTL_SECONDS:
                return self._properties
        self._properties = self.list_properties()
        self._properties_timestamp = time.monotonic()
        return self._properties

    def refresh_properties(self) -> None:
        """Invalidate the cached property type map and force a reload."""
        self._properties = None
        self._properties_timestamp = 0.0

    # --------------------------------------------------------------------- #
    # Prefix helpers
    # --------------------------------------------------------------------- #
    def prefix(self, suffix: str) -> str:
        return f"{self.project_code}_{suffix}"

    def prefix_wd(self) -> str:
        return self.prefix("wd")

    def prefix_wdt(self) -> str:
        return self.prefix("wdt")

    def prefix_pq(self) -> str:
        return self.prefix("pq")

    def prefix_ps(self) -> str:
        return self.prefix("ps")

    def prefix_block(self) -> str:
        """Build and cache the SPARQL PREFIX declarations."""
        if self._prefix_block is None:
            self._prefix_block = (
                f"PREFIX {self.prefix_wd()}: <http://{self.host}/entity/>\n"
                f"PREFIX {self.prefix_wdt()}: <http://{self.host}/prop/direct/>\n"
                f"PREFIX {self.prefix_pq()}: <http://{self.host}/prop/qualifier/>\n"
                f"PREFIX {self.prefix_ps()}: <http://{self.host}/prop/statement/>\n"
            )
        return self._prefix_block

    def with_prefixes(self, query: str) -> str:
        return self.prefix_block() + query

    # --------------------------------------------------------------------- #
    # Wikidata-equivalent IDs
    # --------------------------------------------------------------------- #
    def equivalent_p31(self) -> str:
        return self._cfg_value("WIKIBASE_EQUIVALENT_P31", "P31")

    def equivalent_p1932(self) -> str:
        return self._cfg_value("WIKIBASE_EQUIVALENT_P1932", "P1932")

    def equivalent_q486972(self) -> str:
        return self._cfg_value("WIKIBASE_EQUIVALENT_Q486972", "Q486972")

    # --------------------------------------------------------------------- #
    # SPARQL helper utilities
    # --------------------------------------------------------------------- #
    @staticmethod
    def escape_sparql_literal(value: Any) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace('"', '\\"')
        )

    # --------------------------------------------------------------------- #
    # Date normalization
    # --------------------------------------------------------------------- #
    def normal_dat(self, value: str, *, roman_numerals: bool = True) -> str:
        """Normalize a date string (legacy helper, default Roman numerals on)."""
        normalizer = DateNormalizer(roman_numerals=roman_numerals)
        return normalizer.normalize(value)

    # --------------------------------------------------------------------- #
    # SPARQL lookup helpers
    # --------------------------------------------------------------------- #
    def check_by_label_desc(self, label: str, desc: str, lang: str = "cs"):
        safe_label = self.escape_sparql_literal(label)
        safe_desc = self.escape_sparql_literal(desc)
        query = self.with_prefixes(
            f'SELECT ?item WHERE {{ '
            f'?item rdfs:label "{safe_label}"@{lang}; '
            f'schema:description "{safe_desc}"@{lang}. }}'
        )
        result = sparql(self.sparql_endpoint(), query)
        items = result["results"]["bindings"]
        if len(items) == 0:
            return "create"
        if len(items) == 1:
            return pywikibot.ItemPage(
                self.repo(), items[0]["item"]["value"].split("/")[-1]
            )
        _logger.warning(
            "SPARQL has found more than one item with label %s and description %s: %s",
            label,
            desc,
            [item["item"]["value"] for item in items],
        )
        return None

    def check_id(self, property_id: str, value: str):
        safe_id = self.escape_sparql_literal(value)
        query = self.with_prefixes(
            f'SELECT ?item WHERE {{ ?item {self.prefix_wdt()}:{property_id} "{safe_id}" }}'
        )
        check_id_result = sparql(self.sparql_endpoint(), query)
        result = check_id_result["results"]["bindings"]
        if len(result) == 0:
            return "create"
        if len(result) == 1:
            return pywikibot.ItemPage(
                self.repo(), result[0]["item"]["value"].split("/")[-1]
            )
        _logger.warning("checkID found %s matches for %s=%s", len(result), property_id, value)
        return None

    def label2entity(self, type_id: Optional[str], string: str, lang: str = "cs", limit: int = 10):
        if string == "":
            return None
        safe_string = self.escape_sparql_literal(string)
        type_clause = ""
        if type_id:
            type_clause = (
                f"?item {self.prefix_wdt()}:{self.equivalent_p31()} "
                f"{self.prefix_wd()}:{type_id}."
            )
        query = self.with_prefixes(
            "SELECT DISTINCT ?item WHERE { "
            f"{type_clause} "
            f'?item (rdfs:label|skos:altLabel) "{safe_string}"@{lang}. }}'
            f" LIMIT {limit}"
        )
        result = sparql(self.sparql_endpoint(), query)["results"]["bindings"]
        if len(result) == 1:
            return result[0]["item"]["value"].split("/")[-1]
        return None

    def string2entity(self, property_id: str, string: str, limit: int = 10):
        if string == "":
            return None
        safe_string = self.escape_sparql_literal(string)
        query = self.with_prefixes(
            "SELECT DISTINCT ?item WHERE { "
            f"?statement {self.prefix_pq()}:{self.equivalent_p1932()} \"{safe_string}\"; "
            f"{self.prefix_ps()}:{property_id} ?item. }}"
            f" LIMIT {limit}"
        )
        result = sparql(self.sparql_endpoint(), query)["results"]["bindings"]
        if len(result) == 1:
            return result[0]["item"]["value"].split("/")[-1]
        return None

    # --------------------------------------------------------------------- #
    # Entity editing helpers
    # --------------------------------------------------------------------- #
    def create_item(self, data: dict, summary: str):
        new_item = pywikibot.ItemPage(self.repo())
        try:
            new_item.editEntity(data, summary=summary)
            labels = data.get("labels", {})
            label_value = (
                labels.get("cs")
                or labels.get("de")
                or next(iter(labels.values()), "<no label>")
            )
            _logger.info("Item %s does not exist, created: %s", label_value, new_item)
        except pywikibot.exceptions.OtherPageSaveError as error:
            match = re.search(r"\[\[Item:Q(\d+)\|Q\1\]\]", str(error))
            if match:
                item_exist = match.group(1)
                new_item = pywikibot.ItemPage(self.repo(), f"Q{item_exist}")
            else:
                _logger.error("Failed to create item: %s", error)
                raise
        return new_item

# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **`ClaimBuilder` module** (`lod/claim_builder.py`) — centralizes construction of Wikibase claim and qualifier data dicts for the batch `editEntity` API. Supports `WikibaseItem`, `String`, `ExternalId`, `Url`, `Monolingualtext`, `Time`, and `Quantity` data types.
- **`build_claim_key` helper** (`lod/claim_builder.py`) — generates comparison keys for duplicate detection, including unit only for `Quantity` properties.
- **Unit tests** (`tests/test_claim_builder.py`) — cover all supported property types, qualifier building, and claim-key generation.
- **`ConfigurationError` exception** in `lod/errors.py` — raised when a required configuration value is missing or invalid.
- **`DateNormalizer` module** (`lod/date_normalizer.py`) — refactored date normalization from `lod/wikibase.py` into a dedicated class. Roman numeral handling is now optional (`roman_numerals=False` by default) to avoid accidental mutation of unrelated text.
- **`label2entity` and `string2entity` LIMIT support** — added optional `limit` parameter (default 10) and `lang` parameter for `label2entity` to prevent unbounded SPARQL results.

### Changed

- **`_require_cfg` now raises `ConfigurationError`** instead of `RuntimeError` for missing Wikibase configuration values.
- **`_cfg_value` supports `LOD_` prefixed environment variables** in addition to plain variable names, aligning environment-based configuration with project conventions.
- **`create_item` handles save errors safely** — regex match is now checked before accessing the matched group, preventing `AttributeError` and preserving the original exception when the error message format is unexpected.
- **`update_unique_property` fixes Quantity comparison** — comparison key now includes the unit only for Quantity properties when a unit is provided, avoiding false mismatches for other data types.
- **`add_claim` and `add_qualifier_data` use `ClaimBuilder`** — duplicated datatype handling removed in favor of the centralized builder.
- **`normal_dat` delegates to `DateNormalizer`** — legacy helper retains backward-compatible Roman-numeral behavior while new code can use `DateNormalizer` with safer defaults.
- **`_ensure_properties` caches property list with TTL** — `list_properties()` result is cached for 5 minutes; `refresh_properties()` invalidates the cache.
- **`_wikibase_prefix_block` caches per-project prefix block** — PREFIX declarations are now reused across queries for the same `WIKIBASE_PROJECT_CODE` + `WIKIBASE_HOST` combination.
- **`WikibaseClient`** (`lod/wikibase_client.py`) — new stateful client encapsulating configuration, lazy `site`/`repo` initialization, cached properties, prefix block, and SPARQL/entity editing helpers. Replaces the global mutable state in `lod/wikibase`.
- **Module-level `lod.wikibase` helpers** now delegate `site`/`repo`/`properties` initialization to a default `WikibaseClient` instance while preserving existing public APIs.
- **`DeprecationError` exception** in `lod/errors.py` — raised when a legacy helper or workflow has been replaced by a safer alternative.
- **Legacy pywikibot helpers removed** (`add_qualifier_q`, `add_qualifier_str`, `add_qualifier_dat`, `remove_claim_q`, `remove_claim_str`, `remove_claim_dat`, `remove_qualifier_str`) — these direct `Claim`/`ItemPage` mutating helpers now raise `DeprecationError` pointing users to the batch `data["claims"]` API.
- **Unit tests** (`tests/test_legacy_deprecation.py`) — verify that all removed legacy helpers raise `DeprecationError`.
- **Input validation in `lod.wikibase`** — public helpers now validate property and item IDs using `lod.validation`. Invalid IDs raise `ValidationError` instead of producing malformed SPARQL queries or API payloads.
- **Unit tests** (`tests/test_wikibase_validation.py`) — cover validation errors for `checkID`, `string2entity`, `label2entity`, `add_claim`, `add_claim_loc`, `remove_claim`, `remove_property`, `update_unique_property`, and `get_statement_id`.
- **`add_claim` reference support** — `add_claim` now accepts an optional `references` argument and passes it to `ClaimBuilder`. References can be supplied as `(property_id, value)` tuples or `{"property": ..., "value": ...}` dicts.
- **`ClaimBuilder` reference support** — `build_claim` builds Wikibase reference blocks from simple reference definitions, supporting item, string, URL, and other datatypes used in references.
- **Unit tests** (`tests/test_claim_builder.py`, `tests/test_wikibase.py`) — cover reference construction with tuples and dicts, combinations with qualifiers, and end-to-end `add_claim` integration.

---

## [0.4.2] — 2026-06-26

### Added

- **`remove_property` function** in `lod/wikibase.py` — removes all statements of a given property from an entity.
- **`update_unique_property` function** in `lod/wikibase.py` — updates a single-value property by first comparing the current value, then removing existing statements and adding the new claim when needed.
- **Helper `_get_claim_value`** — extracts comparable values from pywikibot `Claim` targets (string, item, monolingual text, time, quantity).

### Changed

- **`get_statement_id` refactored** in `lod/wikibase.py` — now uses `_get_claim_value` for both mainsnak and qualifier value comparison, removing duplicated type-checking logic. Quantity matching supports both unit-aware (`"500Q11573"`) and amount-only (`"500"`) lookups via `include_unit` flag in `_get_claim_value`.
- **`update_unique_property` refined** in `lod/wikibase.py` — when at least one existing statement already has the target value, it keeps exactly one matching statement and removes only the others (including duplicates). When no matching statement exists, it uses a temporary item with the property cleared so `add_claim` can add the new claim even though the old statements are still present in the live `item.claims` dict.

### Fixed

- **Duplicate-value handling in `update_unique_property`** — previously, removing all statements of a property and then calling `add_claim` could cause the new claim not to be added because `add_claim` still saw the old value in `item.claims`. The function now preserves one matching statement instead of deleting it, and uses a temporary item without the old statements when a new claim must be added.

### Tests

- Extended `tests/test_wikibase.py` with coverage for `get_statement_id` matching string, item, time, quantity (with and without unit), rank, and qualifier values.
- Added tests for `update_unique_property` covering: keeping one matching statement while removing others, handling duplicate matching statements, and replacing multiple non-matching statements without being blocked by the old values.

---

## [0.4.1] — 2026-06-01

### Added

- **`add_qualifier` function** — unified qualifier addition supporting all data types including `Quantity` values as `(amount, unit_qid)` tuples.
- **`add_qualifier_data` function** — builds qualifier data dict for batch API (used internally by `add_claim` with `quals` parameter).

### Changed

- **`add_claim` extended** — added `unit` parameter for Quantity type support; generates proper `amount` + `unit` structure for Wikibase Quantity values.
- **Refactored `add_claim_amount`** — functionality merged into `add_claim` (for batch API) and `add_qualifier` (for direct Pywikibot API).

### Removed

- **`add_claim_amount` function** — use `add_claim(item, data, property, value, unit="Q...")` for batch API or direct `pywikibot.Claim` manipulation for immediate edits.

---

## [0.4.0] — 2026-05-25

### Added

- **RESTful API Client** (`lod.rest.WikibaseRESTClient`) — async HTTP client for direct Wikibase MediaWiki API communication with methods for reading, creating, and updating entities.
- **Async SPARQL support** (`lod.endpoints.sparql_async`, `lod.endpoints.bigData_async`) — non-blocking SPARQL query execution suitable for async frameworks like FastAPI.
- **Error handling module** (`lod.errors`) — comprehensive custom exception hierarchy:
  - `LODError` — base exception
  - `SPARQLError` — SPARQL query execution errors
  - `RateLimitError` — HTTP 429 rate limiting with retry-after support
  - `AuthenticationError` — authentication/authorization failures
  - `EntityNotFoundError` — entity not found (404)
  - `ValidationError` — entity ID or data validation errors
  - `NetworkError` — network communication errors
- **Retry configuration** (`lod.errors.RetryConfig`) — dataclass for configurable retry behavior with exponential backoff, status code filtering, and exception type filtering.
- **Validation utilities** (`lod.validation`) — entity ID validation and URI utilities:
  - `validate_qid()` — validate QID format
  - `validate_pid()` — validate PID format
  - `validate_entity_id()` — validate any entity ID and return type
  - `parse_entity_uri()` — parse entity URI into (type, id) tuple
  - `normalize_uri()` — normalize entity/property IDs to full URIs
  - `extract_entity_id()` — extract entity ID from various formats
- **Batch operations** (`lod.endpoints.batch_iterate`) — utility function for batch processing of results.
- **Comprehensive test suite** — new tests for errors, validation, and REST client modules.

### Changed

- Updated `pyproject.toml` to include `httpx>=0.24.0` as a core dependency.
- Added `pytest-asyncio>=0.21.0` to development dependencies.
- Enhanced `__init__.py` to export all new modules and provide comprehensive docstring.

### Documentation

- Updated README.md with usage examples for REST client, async SPARQL, validation, and error handling.
- Added structure diagram showing all new modules.

---

## [0.3.0] — 2026-04-11

### Added

- **Universal Wikibase prefix model** — SPARQL prefixes are now generated from `WIKIBASE_PROJECT_CODE` + `WIKIBASE_HOST` (or `LOD_WIKIBASE_PROJECT_CODE` + `LOD_WIKIBASE_HOST`).
- **Automatic PREFIX injection** in Wikibase helper queries (`checkID`, `label2entity`, `string2entity`) so generated aliases are always declared in-query.

### Changed

- Prefix aliases now follow deployment-specific names such as `{PROJECT_CODE}_wd`, `{PROJECT_CODE}_wdt`, `{PROJECT_CODE}_pq`, `{PROJECT_CODE}_ps`.
- `WIKIBASE_PROJECT_CODE` and `WIKIBASE_HOST` are now required for Wikibase SPARQL helper functions that rely on these prefixes.
- README configuration examples and reference were rewritten to the new project-code/host model.

### Removed

- Removed legacy prefix overrides `WIKIBASE_PREFIX_WDT`, `WIKIBASE_PREFIX_WD`, `WIKIBASE_PREFIX_PQ`, `WIKIBASE_PREFIX_PS` and corresponding env vars `LOD_WIKIBASE_PREFIX_*`.

### Tests

- Updated Wikibase tests to validate generated project-code prefixes and injected PREFIX declarations.

---

## [0.2.1] — 2026-04-11

### Added

- **`LOD_CONFIG_MODULE` environment variable** — support for loading configuration from a custom Python module without placing it in the project root. Enables centralized configuration management, containerized deployments, and monorepo setups. Fallback to standard `lod_config` module for backward compatibility.
- **New `lod.config_loader` module** — provides `load_config()` function with priority configuration loading chain: `LOD_CONFIG_MODULE` env var → standard `lod_config` module → `None`.
- **`lod.config` attribute** — exported from main `lod` package for direct config module access.
- **Improved configuration logging** — all configuration sources are logged at INFO/DEBUG levels for better debugging and transparency.

### Changed

- **`lod/endpoints.py`** and **`lod/wikibase.py`** now use the new `config_loader.load_config()` instead of direct `importlib` lookups.

### Tests

- Added comprehensive test suite `tests/test_config_loader.py` with 5 tests covering all scenarios (custom module, fallback, priority, error handling).

---

## [0.2.0] — 2026-04-11

### Added

- **Configurable SPARQL prefixes** (`WIKIBASE_PREFIX_WDT`, `WIKIBASE_PREFIX_WD`, `WIKIBASE_PREFIX_PQ`, `WIKIBASE_PREFIX_PS`) — each Wikibase deployment can define its own RDF prefix names; defaults match Wikidata (`wdt`, `wd`, `pq`, `ps`). Readable via env vars (`LOD_WIKIBASE_PREFIX_*`) or `lod_config.py`.
- **Configurable Wikidata-equivalent IDs** (`WIKIBASE_EQUIVALENT_P31`, `WIKIBASE_EQUIVALENT_P1932`, `WIKIBASE_EQUIVALENT_Q486972`) — hard-coded property/entity IDs are now overridable per-project.
- **Retry / back-off for SPARQL requests** — bounded retry loop with exponential back-off; configurable via `SPARQL_MAX_RETRIES`, `SPARQL_RETRY_DELAY`, `SPARQL_BACKOFF_FACTOR` (env vars or `lod_config.py`).
- **`get_bigData` pagination** — accepts `page_size` and `order_by`; raises `ValueError` if the base query already contains `LIMIT`/`OFFSET`.
- **`configure()` runtime API** — accepts all new retry parameters in addition to the existing ones.
- **Lazy Wikibase initialisation** — `site`, `repo`, and `properties` are loaded on first use rather than at import time; `import lod` no longer fails when pywikibot is absent.
- **`pywikibot` moved to optional dependency** — install with `pip install "lod[wikibase]"`.
- **`logging` module** throughout — all `print()` calls replaced with `_logger.info/warning/debug`.
- **SPARQL injection protection** — `_escape_sparql_literal()` applied to all user-supplied string values in SPARQL queries.
- **Regression tests** (`tests/test_endpoints.py`, `tests/test_wikibase.py`) using `unittest`.
- **Full configuration reference** in `README.md`.

### Changed

- Prefix variable names `WIKIBASE_PREFIX_SPQ` → `WIKIBASE_PREFIX_PQ` and `WIKIBASE_PREFIX_SPS` → `WIKIBASE_PREFIX_PS` to align with Wikidata naming (`pq:`, `ps:`).
- `WIKIBASE_EQUIVALENT_P794` renamed to `WIKIBASE_EQUIVALENT_P1932` (P794 no longer exists on Wikidata; replaced by P1932 *object stated as*).
- `label2entity` uses `WIKIBASE_EQUIVALENT_P31` instead of hard-coded `P1`.
- `string2entity` and `add_claim_loc` use `WIKIBASE_EQUIVALENT_P1932` instead of hard-coded `P34`.
- `add_claim_loc` uses `WIKIBASE_EQUIVALENT_Q486972` instead of hard-coded `Q121436`.
- All log messages and comments translated from Czech to English.

### Fixed

- **`checkID` type bug** — `len(result == 1)` (always truthy) corrected to `len(result) == 1`.
- **Infinite retry loop** — unbounded `while True` replaced with `for attempt in range(retries + 1)`.
- **Broad `except Exception`** in `sparql()` narrowed to `(HTTPError, URLError, TimeoutError, ValueError, OSError)`.
- **Bare `except:`** in `add_ref()` replaced with `except pywikibot.exceptions.Error`.
- **`None` qualifier appended without guard** — `add_claim()` now checks `if qual_data is not None` before appending.
- **`properties` parameter shadowing module global** in `add_qualifier()` — renamed to `properties_map`.
- **`== None` identity check** replaced with `is None` throughout.

### Removed

- `dict2entity` removed from the shared library — it is project-specific and belongs in `lod_config.py` (example provided in README).

---

## [0.1.0] — initial release

- Basic SPARQL endpoint helpers (`sparql`, `get_endpoint`, `get_bigData`).
- Basic Wikibase editing helpers (`add_claim`, `create_item`, `add_qualifier`, `add_ref`).
- Built-in endpoints: Wikidata, Wikimedia Commons, FactGrid, QLever OSM/OHM.

# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

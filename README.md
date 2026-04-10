# Linked Open Data Utilities

A Python module with shared helpers for SPARQL endpoint access and Wikibase editing.

## Structure

```text
lod/
├── lod/
│   ├── __init__.py
│   ├── endpoints.py
│   └── wikibase.py
├── pyproject.toml
├── README.md
└── LICENSE
```

## Installation

Core (SPARQL endpoint helpers only):

```bash
pip install git+https://github.com/daelba/lod.git
```

Wikibase helpers require `pywikibot`:

```bash
pip install pywikibot
```

## Usage

```python
from lod import configure, get_endpoint, sparql
from lod.wikibase import add_claim, create_item, properties, repo

result = sparql(get_endpoint("wikidata"), "SELECT * WHERE { ?s ?p ?o } LIMIT 1")
```

## Configuration

Configuration belongs in the **project that uses this module**, not in the module itself.

The following endpoints are available out of the box:

| Key                | URL                                         |
|--------------------|---------------------------------------------|
| `wikidata`         | https://query.wikidata.org/sparql           |
| `commons`          | https://commons-query.wikimedia.org/sparql  |
| `factgrid`         | https://database.factgrid.de/sparql         |
| `qlever_osm_planet`| https://qlever.dev/api/osm-planet           |
| `qlever_ohm_planet`| https://qlever.dev/api/ohm-planet           |

### Option 1 — `lod_config.py` (recommended)

Create a `lod_config.py` file in your project and make sure it is importable
(i.e. on the Python path, typically the project root).
Entries in `ENDPOINTS` are **merged** with the defaults — you only need to list your own endpoints:

```python
# lod_config.py

ENDPOINTS = {
    "src":   "https://src.example.com/sparql",
    "my_wikibase": "https://wikibase.example.com/query/sparql",
}

USER_AGENT = "MyProject/1.0 (contact@example.com)"
TIMEOUT_SECONDS = 60
SPARQL_MAX_RETRIES = 5
SPARQL_RETRY_DELAY = 1.0
SPARQL_BACKOFF_FACTOR = 2.0
WIKIBASE_SITE_CODE = "my_site_code"
WIKIBASE_SITE_FAMILY = "my_site_family"
WIKIBASE_ENDPOINT_KEY = "my_wikibase"
WIKIBASE_PREFIX_WDT = "wdt"
WIKIBASE_PREFIX_WD = "wd"
WIKIBASE_PREFIX_PQ = "pq"
WIKIBASE_PREFIX_PS = "ps"
WIKIBASE_EQUIVALENT_P31     = "P31"    # local equivalent of Wikidata P31 (instance of)
WIKIBASE_EQUIVALENT_P1932   = "P1932"  # local equivalent of Wikidata P1932 (object stated as — original string qualifier)
WIKIBASE_EQUIVALENT_Q486972 = "Q486972" # local equivalent of Wikidata Q486972 (human settlement)
```

### Configuration variable reference

#### SPARQL / endpoint settings

| Variable | Default | Description |
|---|---|---|
| `ENDPOINTS` | built-in set | Dict of `name → URL` entries **merged** with the built-in defaults. |
| `USER_AGENT` | `lod/0.1 …` | HTTP `User-Agent` header sent with every SPARQL request. |
| `TIMEOUT_SECONDS` | `30` | Socket timeout in seconds for each SPARQL HTTP request. |
| `SPARQL_MAX_RETRIES` | `5` | How many times a failed SPARQL request is retried before raising `RuntimeError`. |
| `SPARQL_RETRY_DELAY` | `1.0` | Seconds to wait before the first retry. |
| `SPARQL_BACKOFF_FACTOR` | `2.0` | Multiplier applied to the delay after each consecutive failure (exponential back-off). |

#### Wikibase connection

| Variable | Description |
|---|---|
| `WIKIBASE_ENDPOINT_KEY` | Key in `ENDPOINTS` whose URL is used for Wikibase SPARQL queries (e.g. `"my_wikibase"`). **Required.** |
| `WIKIBASE_SITE_CODE` | First argument of `pywikibot.Site(code, family)` — the site code of your Wikibase installation. **Required.** |
| `WIKIBASE_SITE_FAMILY` | Second argument of `pywikibot.Site(code, family)` — the family name registered in your pywikibot `user-config.py`. **Required.** |

All three connection variables are required for `lod.wikibase`. A missing value raises `RuntimeError` on first use.

#### Wikibase SPARQL prefix variables

Wikibase generates a set of RDF prefixes for each deployment. Their local names follow the same pattern as [Wikidata's SPARQL prefixes](https://en.wikibooks.org/wiki/SPARQL/Prefixes) but differ between installations. The four variables below map each semantic role to the actual prefix name used in your Wikibase.

| Variable | Wikidata equivalent | Semantic role |
|---|---|---|
| `WIKIBASE_PREFIX_WDT` | `wdt:` | **Direct / truthy property** — the most common way to query a statement's value (`?item wdt:P31 wd:Q5`). |
| `WIKIBASE_PREFIX_WD` | `wd:` | **Entity URI** — refers to a specific item or property node (`wd:Q42`, `wd:P31`). |
| `WIKIBASE_PREFIX_PQ` | `pq:` | **Qualifier property** — the predicate used inside a reified statement to attach a qualifier value. |
| `WIKIBASE_PREFIX_PS` | `ps:` | **Statement value property** — the predicate inside a reified statement that holds the main value. |

#### Wikibase entity / property equivalents

The module uses a small number of specific property and entity IDs internally. Each one is configurable via the variables below. The default value equals the Wikidata identifier for the corresponding concept — override only when your Wikibase uses different IDs.

| Variable | Wikidata equivalent | Used in | Role |
|---|---|---|---|
| `WIKIBASE_EQUIVALENT_P31` | P31 | `label2entity` | **Instance of / type** — the property that records what type an entity is (`?item wdt:P31 wd:Q5`). |
| `WIKIBASE_EQUIVALENT_P1932` | P1932 | `string2entity`, `add_claim_loc` | **Object stated as** — qualifier that records the original text string used to find or describe the entity. |
| `WIKIBASE_EQUIVALENT_Q486972` | Q486972 | `add_claim_loc` | **Human settlement** — entity type used as a type filter when resolving a location label to a QID. |

#### Project-specific lookup functions

Some helper functions are too project-specific to live in the shared library and should be defined directly in `lod_config.py`. A typical example is `dict2entity` — a regex-based lookup table that maps raw text strings to Wikibase QIDs for a given property:

```python
# lod_config.py

import re

def dict2entity(prop, string):
    """Convert a raw text value to a Wikibase QID using regex rules per property."""
    replacements = {
        "P_GENDER": {
            r"^m": "Q_MALE",
            r"^[žf]": "Q_FEMALE",
        },
        "P_RELIGION": {
            r"^(římsko|röm)": "Q_ROMAN_CATHOLIC",
            r"^(evan|prot)": "Q_PROTESTANT",
            # … add your own patterns
        },
    }
    for pattern, entity in replacements.get(prop, {}).items():
        if re.match(pattern, string, re.IGNORECASE):
            return entity
    return None
```

Call it from your scripts as `lod_config.dict2entity(prop, string)` (or import it directly).

Add `lod_config.py` to your project's `.gitignore` to keep credentials out of version control.

### Option 2 — `configure()` at runtime

```python
import lod

lod.configure(
    endpoints={"src": "https://src.example.com/sparql"},
    user_agent="MyProject/1.0 (contact@example.com)",
    timeout_seconds=30,
)
```

### Option 3 — environment variables

| Variable            | Overrides        |
|---------------------|------------------|
| `LOD_USER_AGENT`    | `USER_AGENT`     |
| `LOD_SPARQL_TIMEOUT`| `TIMEOUT_SECONDS`|
| `LOD_SPARQL_MAX_RETRIES` | `SPARQL_MAX_RETRIES` |
| `LOD_SPARQL_RETRY_DELAY` | `SPARQL_RETRY_DELAY` |
| `LOD_SPARQL_BACKOFF_FACTOR` | `SPARQL_BACKOFF_FACTOR` |
| `LOD_WIKIBASE_SITE_CODE` | `WIKIBASE_SITE_CODE` |
| `LOD_WIKIBASE_SITE_FAMILY` | `WIKIBASE_SITE_FAMILY` |
| `LOD_WIKIBASE_ENDPOINT_KEY` | `WIKIBASE_ENDPOINT_KEY` |
| `LOD_WIKIBASE_PREFIX_WDT` | `WIKIBASE_PREFIX_WDT` |
| `LOD_WIKIBASE_PREFIX_WD` | `WIKIBASE_PREFIX_WD` |
| `LOD_WIKIBASE_PREFIX_PQ` | `WIKIBASE_PREFIX_PQ` |
| `LOD_WIKIBASE_PREFIX_PS` | `WIKIBASE_PREFIX_PS` |
| `LOD_WIKIBASE_EQUIVALENT_P31` | `WIKIBASE_EQUIVALENT_P31` |
| `LOD_WIKIBASE_EQUIVALENT_P1932` | `WIKIBASE_EQUIVALENT_P1932` |
| `LOD_WIKIBASE_EQUIVALENT_Q486972` | `WIKIBASE_EQUIVALENT_Q486972` |

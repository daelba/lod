# Linked Open Data Utilities

A Python module with shared helpers for SPARQL endpoint access and Wikibase editing.

## Structure

```text
lod/
├── lod/
│   ├── __init__.py          # Main public API
│   ├── config_loader.py     # Configuration loading
│   ├── default_endpoints.json
│   ├── endpoints.py         # SPARQL functions (sync & async)
│   ├── errors.py            # Custom exceptions & retry config
│   ├── rest.py              # RESTful API client for Wikibase
│   ├── validation.py        # Entity ID validation utilities
│   └── wikibase.py          # Pywikibot-based editing
├── tests/
│   ├── test_config_loader.py
│   ├── test_endpoints.py
│   ├── test_errors.py
│   ├── test_rest.py
│   ├── test_validation.py
│   └── test_wikibase.py
├── pyproject.toml
├── README.md
└── LICENSE
```

## Installation

Core (SPARQL endpoint helpers + REST client):

```bash
pip install git+https://github.com/daelba/lod.git
```

Wikibase helpers require `pywikibot`:

```bash
pip install pywikibot
```

Development dependencies (for running tests):

```bash
pip install pytest pytest-asyncio
```

## Usage

### SPARQL Queries (Synchronous)

```python
from lod import sparql, get_endpoint

result = sparql(get_endpoint("wikidata"), "SELECT * WHERE { ?s ?p ?o } LIMIT 10")
for binding in result["results"]["bindings"]:
    print(binding)
```

### SPARQL Queries (Asynchronous)

```python
import asyncio
from lod import sparql_async, get_endpoint

async def main():
    result = await sparql_async(
        get_endpoint("wikidata"),
        "SELECT * WHERE { ?s ?p ?o } LIMIT 10"
    )
    for binding in result["results"]["bindings"]:
        print(binding)

asyncio.run(main())
```

### REST API Client

```python
import asyncio
from lod.rest import WikibaseRESTClient

async def main():
    async with WikibaseRESTClient("https://www.wikidata.org") as client:
        # Get an item
        item = await client.get_item("Q486972")
        print(item["labels"]["en"]["value"])
        
        # Search for entities
        results = await client.search_entities("Praha", language="cs")
        for r in results:
            print(f"{r['id']}: {r['label']}")

asyncio.run(main())
```

### Entity Validation

```python
from lod import validate_qid, validate_pid, normalize_uri, extract_entity_id

# Validate entity IDs
assert validate_qid("Q486972") is True
assert validate_pid("P31") is True

# Normalize URIs
uri = normalize_uri("Q123")
# Returns: "http://www.wikidata.org/entity/Q123"

# Extract entity IDs from various formats
extract_entity_id("wd:Q486972")  # Returns: "Q486972"
extract_entity_id("http://www.wikidata.org/entity/Q123")  # Returns: "Q123"
```

### Error Handling

```python
from lod import (
    LODError, SPARQLError, RateLimitError, 
    AuthenticationError, EntityNotFoundError, 
    NetworkError, RetryConfig
)

try:
    result = sparql(endpoint, query, max_retries=3)
except RateLimitError as e:
    print(f"Rate limited. Retry after: {e.retry_after} seconds")
except EntityNotFoundError as e:
    print(f"Entity not found: {e.entity_id}")
except SPARQLError as e:
    print(f"SPARQL error: {e.message}")
    print(f"Query: {e.query}")
    print(f"Endpoint: {e.endpoint}")
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

### Option 0 — `LOD_CONFIG_MODULE` environment variable

To use a custom configuration module without placing it in the project root, set the `LOD_CONFIG_MODULE`
environment variable to the fully qualified Python module name:

```bash
export LOD_CONFIG_MODULE=myproject.config.settings
python your_script.py
```

Or in Python code (must be set **before importing**):

```python
import os
os.environ['LOD_CONFIG_MODULE'] = 'myproject.config.settings'

import lod
# Now lod will load configuration from myproject.config.settings
```

If `LOD_CONFIG_MODULE` is not set, `lod` falls back to the standard `lod_config` module for backward compatibility.

This approach is useful for:
- Containerized applications or microservices (set in Docker Compose / Kubernetes)
- Projects with centralized configuration management
- Monorepos where each service has its own config module path

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
WIKIBASE_PROJECT_CODE = "mywiki"
WIKIBASE_HOST = "wikibase.example.com"
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

Prefix aliases are generated automatically from two variables:
- `WIKIBASE_PROJECT_CODE` (for example `fg`, `mywiki`)
- `WIKIBASE_HOST` (for example `database.factgrid.de`, `wikibase.example.com`)

Example generated aliases for `WIKIBASE_PROJECT_CODE="fg"` and `WIKIBASE_HOST="database.factgrid.de"`:

```sparql
PREFIX fg_wd:  <http://database.factgrid.de/entity/>
PREFIX fg_wdt: <http://database.factgrid.de/prop/direct/>
PREFIX fg_pq:  <http://database.factgrid.de/prop/qualifier/>
PREFIX fg_ps:  <http://database.factgrid.de/prop/statement/>
```

This corresponds to Wikidata-style roles (`wd`, `wdt`, `pq`, `ps`) but remains deployment-agnostic.

Primary variables:

| Variable | Description |
|---|---|
| `WIKIBASE_PROJECT_CODE` | Prefix base used to build aliases (`{PROJECT_CODE}_wd`, `{PROJECT_CODE}_wdt`, `{PROJECT_CODE}_pq`, `{PROJECT_CODE}_ps`). |
| `WIKIBASE_HOST` | Host used to build namespace IRIs (`http://{WIKIBASE_HOST}/entity/`, `.../prop/direct/`, `.../prop/qualifier/`, `.../prop/statement/`). |

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

Environment variables use the same names as configuration variables:

| Variable                     | Overrides                    |
|------------------------------|------------------------------|
| `USER_AGENT`                 | `USER_AGENT`                 |
| `SPARQL_TIMEOUT`             | `TIMEOUT_SECONDS`            |
| `SPARQL_MAX_RETRIES`         | `SPARQL_MAX_RETRIES`         |
| `SPARQL_RETRY_DELAY`         | `SPARQL_RETRY_DELAY`         |
| `SPARQL_BACKOFF_FACTOR`      | `SPARQL_BACKOFF_FACTOR`      |
| `WIKIBASE_SITE_CODE`         | `WIKIBASE_SITE_CODE`         |
| `WIKIBASE_SITE_FAMILY`       | `WIKIBASE_SITE_FAMILY`       |
| `WIKIBASE_ENDPOINT_KEY`      | `WIKIBASE_ENDPOINT_KEY`      |
| `WIKIBASE_PROJECT_CODE`      | `WIKIBASE_PROJECT_CODE`      |
| `WIKIBASE_HOST`              | `WIKIBASE_HOST`              |
| `WIKIBASE_EQUIVALENT_P31`    | `WIKIBASE_EQUIVALENT_P31`    |
| `WIKIBASE_EQUIVALENT_P1932`  | `WIKIBASE_EQUIVALENT_P1932`  |
| `WIKIBASE_EQUIVALENT_Q486972`| `WIKIBASE_EQUIVALENT_Q486972`|

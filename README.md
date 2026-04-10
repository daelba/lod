# lod

Shared Python helpers for SPARQL endpoint access and Wikibase editing.

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

```bash
pip install git+https://github.com/daelba/lod.git
```

## Usage

```python
from lod.endpoints import endpoint_wd, sparql
from lod.wikibase import add_claim, create_item, properties, repo
```

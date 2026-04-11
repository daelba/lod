"""Public API for the lod helper package."""

import warnings

from .config_loader import load_config
from .endpoints import ENDPOINTS, configure, get_bigData, get_endpoint, sparql

# Load and export configuration
config = load_config()

_DEPRECATED_ENDPOINT_ALIASES = {
    "endpoint_src": "src",
    "endpoint_scrap": "scrap",
    "endpoint_wd": "wikidata",
    "endpoint_fg": "factgrid",
    "endpoint_gotha": "gotha",
}

_WIKIBASE_EXPORTS = {
    "add_claim",
    "create_item",
    "properties",
    "repo",
}


def __getattr__(name):
    if name in _DEPRECATED_ENDPOINT_ALIASES:
        warnings.warn(
            f"{name} is deprecated and will be removed in the next version. "
            "Use get_endpoint(...) or ENDPOINTS[...] instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return get_endpoint(_DEPRECATED_ENDPOINT_ALIASES[name])

    if name in _WIKIBASE_EXPORTS:
        from . import wikibase

        return getattr(wikibase, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ENDPOINTS",
    "config",
    "configure",
    "endpoint_fg",
    "endpoint_gotha",
    "endpoint_scrap",
    "endpoint_src",
    "endpoint_wd",
    "get_bigData",
    "get_endpoint",
    "sparql",
    "add_claim",
    "create_item",
    "properties",
    "repo",
]

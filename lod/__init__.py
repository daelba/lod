"""Public API for the lod helper package.

This package provides tools for working with Linked Open Data (LOD),
particularly Wikibase instances and SPARQL endpoints.

Main components:
    - endpoints: SPARQL query functions (sync and async)
    - rest: RESTful API client for Wikibase
    - errors: Custom exceptions and retry configuration
    - validation: Entity ID validation and URI utilities
    - wikibase: Pywikibot-based entity operations

Example usage:
    >>> from lod import sparql, get_endpoint
    >>> result = sparql(get_endpoint("wikidata"), "SELECT * WHERE { ?s ?p ?o } LIMIT 10")

    >>> import asyncio
    >>> from lod.rest import WikibaseRESTClient
    >>> async def main():
    ...     async with WikibaseRESTClient("https://www.wikidata.org") as client:
    ...         item = await client.get_item("Q486972")
    >>> asyncio.run(main())
"""

import warnings

from .config_loader import load_config
from .endpoints import (
    ENDPOINTS,
    batch_iterate,
    bigData_async,
    configure,
    get_bigData,
    get_endpoint,
    sparql,
    sparql_async,
)

# Import error types for convenient access
from .errors import (
    LODError,
    SPARQLError,
    RateLimitError,
    AuthenticationError,
    EntityNotFoundError,
    ValidationError,
    NetworkError,
    RetryConfig,
    DEFAULT_RETRY_CONFIG,
)

# Import validation utilities
from .validation import (
    validate_qid,
    validate_pid,
    validate_entity_id,
    parse_entity_uri,
    normalize_uri,
    extract_entity_id,
)

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
    # Core functions
    "sparql",
    "sparql_async",
    "get_endpoint",
    "get_bigData",
    "bigData_async",
    "batch_iterate",
    "configure",
    "ENDPOINTS",
    "config",
    # Error types
    "LODError",
    "SPARQLError",
    "RateLimitError",
    "AuthenticationError",
    "EntityNotFoundError",
    "ValidationError",
    "NetworkError",
    "RetryConfig",
    "DEFAULT_RETRY_CONFIG",
    # Validation functions
    "validate_qid",
    "validate_pid",
    "validate_entity_id",
    "parse_entity_uri",
    "normalize_uri",
    "extract_entity_id",
    # Deprecated (backward compatibility)
    "endpoint_fg",
    "endpoint_gotha",
    "endpoint_scrap",
    "endpoint_src",
    "endpoint_wd",
    # Wikibase (pywikibot-based)
    "add_claim",
    "create_item",
    "properties",
    "repo",
]
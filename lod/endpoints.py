import asyncio
import importlib
import json
import logging
import os
import re
import time
import warnings
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config_loader import load_config

############### SPARQL functions ###############

DEFAULT_ENDPOINTS_FILE = Path(__file__).with_name("default_endpoints.json")
DEFAULT_USER_AGENT = "lod/0.1 (+https://github.com/daelba/lod)"
_logger = logging.getLogger(__name__)

# Load user configuration using config_loader
_user_cfg = load_config()


def _load_default_endpoints(file_path=DEFAULT_ENDPOINTS_FILE):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Default endpoint configuration must be a JSON object")

    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Each default endpoint name and URL must be a string")

    return data


def _get_int(name, value, minimum=1):
    parsed = int(value)
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


def _get_float(name, value, minimum=0.0):
    parsed = float(value)
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


DEFAULT_ENDPOINTS = _load_default_endpoints()


def _build_config():
    env_timeout = os.getenv("LOD_SPARQL_TIMEOUT")
    env_retries = os.getenv("LOD_SPARQL_MAX_RETRIES")
    env_retry_delay = os.getenv("LOD_SPARQL_RETRY_DELAY")
    env_backoff = os.getenv("LOD_SPARQL_BACKOFF_FACTOR")

    endpoints = dict(DEFAULT_ENDPOINTS)
    endpoints.update(getattr(_user_cfg, "ENDPOINTS", {}) if _user_cfg else {})

    timeout_value = (
        env_timeout
        if env_timeout is not None
        else (getattr(_user_cfg, "TIMEOUT_SECONDS", None) if _user_cfg else None)
    )
    retry_count_value = (
        env_retries
        if env_retries is not None
        else (getattr(_user_cfg, "SPARQL_MAX_RETRIES", None) if _user_cfg else None)
    )
    retry_delay_value = (
        env_retry_delay
        if env_retry_delay is not None
        else (getattr(_user_cfg, "SPARQL_RETRY_DELAY", None) if _user_cfg else None)
    )
    backoff_factor_value = (
        env_backoff
        if env_backoff is not None
        else (getattr(_user_cfg, "SPARQL_BACKOFF_FACTOR", None) if _user_cfg else None)
    )

    return {
        "endpoints": endpoints,
        "user_agent": (
            os.getenv("LOD_USER_AGENT")
            or (getattr(_user_cfg, "USER_AGENT", None) if _user_cfg else None)
            or DEFAULT_USER_AGENT
        ),
        "timeout_seconds": _get_int("timeout_seconds", timeout_value or 60),
        "max_retries": _get_int("max_retries", retry_count_value or 5, minimum=0),
        "retry_delay_seconds": _get_float("retry_delay_seconds", retry_delay_value or 1.0, minimum=0.0),
        "backoff_factor": _get_float("backoff_factor", backoff_factor_value or 2.0, minimum=1.0),
    }


_CONFIG = _build_config()
ENDPOINTS = _CONFIG["endpoints"]


def configure(
    *,
    endpoints=None,
    user_agent=None,
    timeout_seconds=None,
    max_retries=None,
    retry_delay_seconds=None,
    backoff_factor=None,
):
    """Override configuration at runtime (alternative to lod_config.py)."""
    global ENDPOINTS
    if endpoints is not None:
        _CONFIG["endpoints"].update(endpoints)
        ENDPOINTS = _CONFIG["endpoints"]
    if user_agent is not None:
        _CONFIG["user_agent"] = user_agent or DEFAULT_USER_AGENT
    if timeout_seconds is not None:
        _CONFIG["timeout_seconds"] = _get_int("timeout_seconds", timeout_seconds)
    if max_retries is not None:
        _CONFIG["max_retries"] = _get_int("max_retries", max_retries, minimum=0)
    if retry_delay_seconds is not None:
        _CONFIG["retry_delay_seconds"] = _get_float("retry_delay_seconds", retry_delay_seconds, minimum=0.0)
    if backoff_factor is not None:
        _CONFIG["backoff_factor"] = _get_float("backoff_factor", backoff_factor, minimum=1.0)


def get_endpoint(name):
    return ENDPOINTS[name]


_DEPRECATED_ENDPOINT_ALIASES = {
    "endpoint_src": "src",
    "endpoint_scrap": "scrap",
    "endpoint_wd": "wikidata",
    "endpoint_fg": "factgrid",
    "endpoint_gotha": "gotha",
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def sparql(
    endpoint,
    query,
    *,
    timeout_seconds=None,
    max_retries=None,
    retry_delay_seconds=None,
    backoff_factor=None,
):
    payload = urlencode({"query": query}).encode("utf-8")
    headers = {
        "User-Agent": _CONFIG["user_agent"],
        "Accept": "application/sparql-results+json, application/json",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }

    effective_timeout = (
        _CONFIG["timeout_seconds"] if timeout_seconds is None else _get_int("timeout_seconds", timeout_seconds)
    )
    effective_retries = (
        _CONFIG["max_retries"] if max_retries is None else _get_int("max_retries", max_retries, minimum=0)
    )
    effective_delay = (
        _CONFIG["retry_delay_seconds"]
        if retry_delay_seconds is None
        else _get_float("retry_delay_seconds", retry_delay_seconds, minimum=0.0)
    )
    effective_backoff = (
        _CONFIG["backoff_factor"]
        if backoff_factor is None
        else _get_float("backoff_factor", backoff_factor, minimum=1.0)
    )

    for attempt in range(effective_retries + 1):
        try:
            request = Request(endpoint, data=payload, headers=headers, method="POST")
            with urlopen(request, timeout=effective_timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset))
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
            if attempt >= effective_retries:
                raise RuntimeError(
                    f"SPARQL query failed after {effective_retries + 1} attempts"
                ) from error
            delay = effective_delay * (effective_backoff ** attempt)
            _logger.warning(
                "SPARQL endpoint query failed (attempt %s/%s): %s. Retrying in %.2fs",
                attempt + 1,
                effective_retries + 1,
                error,
                delay,
            )
            time.sleep(delay)


async def sparql_async(
    endpoint: str,
    query: str,
    *,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_delay_seconds: Optional[float] = None,
    backoff_factor: Optional[float] = None,
) -> Dict[str, Any]:
    """Async version of sparql() using httpx.

    This function provides non-blocking SPARQL query execution, suitable for
    use in async frameworks like FastAPI.

    Args:
        endpoint: SPARQL endpoint URL.
        query: SPARQL query string.
        timeout_seconds: Optional timeout override.
        max_retries: Optional retry count override.
        retry_delay_seconds: Optional initial retry delay.
        backoff_factor: Optional backoff multiplier.

    Returns:
        Dictionary containing SPARQL results in JSON format.

    Raises:
        RuntimeError: If query fails after all retry attempts.

    Example:
        >>> import asyncio
        >>> from lod.endpoints import sparql_async, get_endpoint
        >>>
        >>> async def main():
        ...     result = await sparql_async(
        ...         get_endpoint("wikidata"),
        ...         "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 } LIMIT 10"
        ...     )
        ...     print(result["results"]["bindings"])
        >>>
        >>> asyncio.run(main())
    """
    import httpx

    payload = {"query": query}
    headers = {
        "User-Agent": _CONFIG["user_agent"],
        "Accept": "application/sparql-results+json, application/json",
    }

    effective_timeout = (
        _CONFIG["timeout_seconds"] if timeout_seconds is None else _get_int("timeout_seconds", timeout_seconds)
    )
    effective_retries = (
        _CONFIG["max_retries"] if max_retries is None else _get_int("max_retries", max_retries, minimum=0)
    )
    effective_delay = (
        _CONFIG["retry_delay_seconds"]
        if retry_delay_seconds is None
        else _get_float("retry_delay_seconds", retry_delay_seconds, minimum=0.0)
    )
    effective_backoff = (
        _CONFIG["backoff_factor"]
        if backoff_factor is None
        else _get_float("backoff_factor", backoff_factor, minimum=1.0)
    )

    async with httpx.AsyncClient(timeout=httpx.Timeout(effective_timeout)) as client:
        for attempt in range(effective_retries + 1):
            try:
                response = await client.post(
                    endpoint,
                    params=payload,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if attempt >= effective_retries:
                    raise RuntimeError(
                        f"SPARQL query failed after {effective_retries + 1} attempts: {e}"
                    ) from e
                delay = effective_delay * (effective_backoff**attempt)
                _logger.warning(
                    "SPARQL endpoint query failed (attempt %s/%s): %s. Retrying in %.2fs",
                    attempt + 1,
                    effective_retries + 1,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)

            except httpx.RequestError as e:
                if attempt >= effective_retries:
                    raise RuntimeError(
                        f"SPARQL query failed after {effective_retries + 1} attempts: {e}"
                    ) from e
                delay = effective_delay * (effective_backoff**attempt)
                _logger.warning(
                    "SPARQL endpoint request error (attempt %s/%s): %s. Retrying in %.2fs",
                    attempt + 1,
                    effective_retries + 1,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)

    # Should not reach here
    raise RuntimeError(f"SPARQL query failed after {effective_retries + 1} attempts")


async def bigData_async(
    endpoint: str,
    query: str,
    *,
    page_size: int = 10000,
    order_by: Optional[str] = None,
    max_concurrent: int = 1,
) -> AsyncIterator[Dict[str, Any]]:
    """Async generator for paginated large result sets.

    This function yields results in batches, allowing for memory-efficient
    processing of large SPARQL result sets.

    Args:
        endpoint: SPARQL endpoint URL.
        query: Base SPARQL query (without LIMIT/OFFSET).
        page_size: Number of results per page (default: 10000).
        order_by: ORDER BY clause for consistent ordering.
        max_concurrent: Maximum concurrent requests (currently always 1).

    Yields:
        Individual result bindings (dictionaries).

    Raises:
        ValueError: If page_size <= 0 or query contains LIMIT/OFFSET.

    Example:
        >>> import asyncio
        >>> from lod.endpoints import bigData_async, get_endpoint
        >>>
        >>> async def main():
        ...     async for item in bigData_async(
        ...         get_endpoint("wikidata"),
        ...         "SELECT ?item WHERE { ?item wdt:P31 wd:Q5 }",
        ...         page_size=1000,
        ...     ):
        ...         print(item)
        >>>
        >>> asyncio.run(main())
    """
    if _get_int("page_size", page_size) <= 0:
        raise ValueError("page_size must be > 0")

    if re.search(r"\b(limit|offset)\b", query, flags=re.IGNORECASE):
        raise ValueError("Base query for bigData_async must not contain LIMIT/OFFSET")

    offset = 0
    order_clause = f"ORDER BY {order_by}" if order_by else ""

    while True:
        query_offset = f"{query}\n{order_clause}\nLIMIT {page_size}\nOFFSET {offset}"

        result = await sparql_async(endpoint, query_offset)
        bindings = result.get("results", {}).get("bindings", [])

        if not bindings:
            _logger.info("Found %s total results", offset)
            return

        for item in bindings:
            yield item

        offset += page_size


def get_bigData(
    endpoint: str,
    query: str,
    *,
    page_size: int = 10000,
    order_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get large result sets with pagination (legacy synchronous version).

    Note: For async usage, prefer bigData_async().

    Args:
        endpoint: SPARQL endpoint URL.
        query: Base SPARQL query (without LIMIT/OFFSET).
        page_size: Number of results per page (default: 10000).
        order_by: ORDER BY clause for consistent ordering.

    Returns:
        List of all result bindings.

    Raises:
        ValueError: If page_size <= 0 or query contains LIMIT/OFFSET.
    """
    if _get_int("page_size", page_size) <= 0:
        raise ValueError("page_size must be > 0")

    if re.search(r"\b(limit|offset)\b", query, flags=re.IGNORECASE):
        raise ValueError("Base query for get_bigData must not contain LIMIT/OFFSET")

    items: List[Dict[str, Any]] = []
    offset = 0
    order_clause = f"ORDER BY {order_by}" if order_by else ""

    while True:
        query_offset = (
            f"{query}\n"
            f"{order_clause}\n"
            f"LIMIT {page_size}\n"
            f"OFFSET {offset}"
        )

        result = sparql(endpoint, query_offset)["results"]["bindings"]
        if not result:
            _logger.info("Found %s results", len(items))
            return items

        items.extend(result)
        offset += page_size


def batch_iterate(
    items: List[Any], batch_size: int = 100
) -> Iterator[List[Any]]:
    """Iterate over items in batches.

    Utility function for batch processing of SPARQL results or other data.

    Args:
        items: List of items to batch.
        batch_size: Maximum items per batch.

    Yields:
        Lists of items, each with at most batch_size elements.

    Example:
        >>> results = sparql(endpoint, query)["results"]["bindings"]
        >>> for batch in batch_iterate(results, batch_size=50):
        ...     process_batch(batch)
    """
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]

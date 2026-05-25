"""Entity ID validation and resolution utilities.

This module provides functions for validating and resolving Wikibase
entity IDs (QIDs and PIDs) and working with entity URIs.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from .errors import ValidationError


# Regex patterns for entity ID validation
_QID_PATTERN = re.compile(r"^Q\d+$", re.IGNORECASE)
_PID_PATTERN = re.compile(r"^P\d+$", re.IGNORECASE)
_ENTITY_URI_PATTERN = re.compile(
    r"^https?://[^/]+/(?:entity|property| Entity)/([QP]\d+)$", re.IGNORECASE
)


def validate_qid(qid: str) -> bool:
    """Validate QID format (Q followed by digits).

    Args:
        qid: The entity ID to validate.

    Returns:
        True if the QID format is valid.

    Examples:
        >>> validate_qid("Q486972")
        True
        >>> validate_qid("Q1")
        True
        >>> validate_qid("q123")  # lowercase is valid
        True
        >>> validate_qid("P31")
        False
        >>> validate_qid("Q")
        False
        >>> validate_qid("Qabc")
        False
    """
    if not isinstance(qid, str):
        return False
    return bool(_QID_PATTERN.match(qid.upper()))


def validate_pid(pid: str) -> bool:
    """Validate Property ID format (P followed by digits).

    Args:
        pid: The property ID to validate.

    Returns:
        True if the PID format is valid.

    Examples:
        >>> validate_pid("P31")
        True
        >>> validate_pid("P8")
        True
        >>> validate_pid("p31")  # lowercase is valid
        True
        >>> validate_pid("Q486972")
        False
        >>> validate_pid("P")
        False
        >>> validate_pid("Pabc")
        False
    """
    if not isinstance(pid, str):
        return False
    return bool(_PID_PATTERN.match(pid.upper()))


def validate_entity_id(entity_id: str) -> Tuple[bool, Optional[str]]:
    """Validate any entity ID and return its type.

    Args:
        entity_id: The entity ID to validate.

    Returns:
        Tuple of (is_valid, entity_type) where entity_type is 'item', 'property', or None.

    Examples:
        >>> validate_entity_id("Q486972")
        (True, 'item')
        >>> validate_entity_id("P31")
        (True, 'property')
        >>> validate_entity_id("invalid")
        (False, None)
    """
    if not isinstance(entity_id, str):
        return (False, None)

    if _QID_PATTERN.match(entity_id.upper()):
        return (True, "item")
    elif _PID_PATTERN.match(entity_id.upper()):
        return (True, "property")
    else:
        return (False, None)


def parse_entity_uri(uri: str) -> Tuple[str, str]:
    """Parse entity URI into (type, id) tuple.

    Supports various URI formats from different Wikibase instances:
    - http://www.wikidata.org/entity/Q486972
    - https://query.wikidata.org/entity/Q486972
    - http://www.wikidata.org/prop/direct/P31
    - https://www.wikibase.cloud/entity/Q123

    Args:
        uri: The full entity URI to parse.

    Returns:
        Tuple of (entity_type, entity_id) where entity_type is 'Q' or 'P'.

    Raises:
        ValidationError: If the URI cannot be parsed.

    Examples:
        >>> parse_entity_uri("http://www.wikidata.org/entity/Q486972")
        ('Q', 'Q486972')
        >>> parse_entity_uri("http://www.wikidata.org/prop/direct/P31")
        ('P', 'P31')
        >>> parse_entity_uri("invalid-uri")
        Traceback (most recent call last):
            ...
        ValidationError: Cannot parse entity URI
    """
    if not isinstance(uri, str):
        raise ValidationError("URI must be a string", field="uri", value=str(uri))

    # Try the regex pattern first
    match = _ENTITY_URI_PATTERN.match(uri)
    if match:
        entity_id = match.group(1).upper()
        entity_type = entity_id[0].upper()
        return (entity_type, entity_id)

    # Try manual parsing as fallback
    try:
        parsed = urlparse(uri)
        path_parts = [p for p in parsed.path.split("/") if p]

        if not path_parts:
            raise ValidationError(
                "Cannot parse entity URI: empty path", field="uri", value=uri
            )

        # Look for entity ID in path
        for part in path_parts:
            part_upper = part.upper()
            if _QID_PATTERN.match(part_upper):
                return ("Q", part_upper)
            elif _PID_PATTERN.match(part_upper):
                return ("P", part_upper)

        raise ValidationError(
            f"Cannot parse entity URI: no valid entity ID found", field="uri", value=uri
        )

    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(
            f"Cannot parse entity URI: {str(e)}", field="uri", value=uri
        ) from e


def normalize_uri(
    entity_id: str, project_code: str = "wikidata", base_url: Optional[str] = None
) -> str:
    """Normalize entity/property URI across different Wikibase instances.

    Converts entity IDs to their full URIs using standard Wikibase URL patterns.

    Args:
        entity_id: The entity ID (e.g., 'Q486972', 'P31').
        project_code: Project code for default URL construction.
                     Common values: 'wikidata', 'wikibase'.
        base_url: Optional base URL to override default project URLs.
                 If provided, takes precedence over project_code.

    Returns:
        Full entity URI (e.g., 'http://www.wikidata.org/entity/Q486972').

    Raises:
        ValidationError: If entity_id format is invalid.

    Examples:
        >>> normalize_uri("Q486972")
        'http://www.wikidata.org/entity/Q486972'
        >>> normalize_uri("P31")
        'http://www.wikidata.org/prop/direct/P31'
        >>> normalize_uri("Q123", project_code="wikibase")
        'http://wikibase.example/entity/Q123'
        >>> normalize_uri("Q123", base_url="https://my.wikibase.cloud")
        'https://my.wikibase.cloud/entity/Q123'
    """
    if not isinstance(entity_id, str):
        raise ValidationError("Entity ID must be a string", field="entity_id", value=str(entity_id))

    entity_id = entity_id.upper()
    is_valid, entity_type = validate_entity_id(entity_id)
    if not is_valid:
        raise ValidationError(
            f"Invalid entity ID: {entity_id}", field="entity_id", value=entity_id
        )

    # Determine base URL
    if base_url:
        base = base_url.rstrip("/")
    elif project_code.lower() == "wikidata":
        base = "http://www.wikidata.org"
    else:
        # Generic fallback
        base = f"http://{project_code.lower()}.wikibase.cloud"

    # Construct URI based on entity type
    if entity_type == "item":
        return f"{base}/entity/{entity_id}"
    elif entity_type == "property":
        return f"{base}/prop/direct/{entity_id}"
    else:
        # Should not reach here due to validation
        return f"{base}/entity/{entity_id}"


def extract_entity_id(value: str) -> Optional[str]:
    """Extract entity ID from various formats.

    This function attempts to extract a clean entity ID from various input formats:
    - Plain entity ID: "Q486972" -> "Q486972"
    - Full URI: "http://www.wikidata.org/entity/Q486972" -> "Q486972"
    - With prefix: "wd:Q486972" -> "Q486972"
    - Curly braces: "{Q486972}" -> "Q486972"

    Args:
        value: The input string potentially containing an entity ID.

    Returns:
        Extracted entity ID in uppercase format, or None if not found.

    Examples:
        >>> extract_entity_id("Q486972")
        'Q486972'
        >>> extract_entity_id("http://www.wikidata.org/entity/Q486972")
        'Q486972'
        >>> extract_entity_id("wd:Q486972")
        'Q486972'
        >>> extract_entity_id("{Q123}")
        'Q123'
        >>> extract_entity_id("not an entity")
        None
    """
    if not isinstance(value, str):
        return None

    # Clean up common prefixes/suffixes
    cleaned = value.strip().strip("{}[]()")

    # Remove common prefixes
    for prefix in ["wd:", "wdt:", "pq:", "ps:", "p:", "q:", "http://", "https://"]:
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]

    # Extract entity ID pattern from remaining string
    match = re.search(r"([QP]\d+)", cleaned, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    return None


async def resolve_entity(
    endpoint: str, entity_id: str, sparql_func=None
) -> Optional[Dict]:
    """Check if entity exists and return its metadata.

    This function queries the SPARQL endpoint to verify that an entity exists
    and retrieves basic metadata about it.

    Args:
        endpoint: SPARQL endpoint URL.
        entity_id: The entity ID to resolve.
        sparql_func: Optional SPARQL function to use. Defaults to lod.endpoints.sparql.

    Returns:
        Dictionary with entity metadata if found, None otherwise.
        The dict contains: id, type, label (if available), uri

    Raises:
        ValidationError: If entity_id format is invalid.

    Example:
        >>> from lod.endpoints import sparql, get_endpoint
        >>> entity = await resolve_entity(get_endpoint("wikidata"), "Q486972", sparql)
        >>> if entity:
        ...     print(f"Found: {entity['label']}")
    """
    # Import here to avoid circular imports
    if sparql_func is None:
        from .endpoints import sparql

        sparql_func = sparql

    is_valid, entity_type = validate_entity_id(entity_id)
    if not is_valid:
        raise ValidationError(
            f"Invalid entity ID: {entity_id}", field="entity_id", value=entity_id
        )

    # Build query based on entity type
    if entity_type == "item":
        query = f"""
        SELECT ?item ?itemLabel WHERE {{
          VALUES ?item {{ wd:{entity_id.upper()} }}
          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "[AUTO_LANGUAGE],cs,en" .
          }}
        }}
        LIMIT 1
        """
    else:  # property
        query = f"""
        SELECT ?property ?propertyLabel WHERE {{
          VALUES ?property {{ wd:{entity_id.upper()} }}
          SERVICE wikibase:label {{
            bd:serviceParam wikibase:language "[AUTO_LANGUAGE],cs,en" .
          }}
        }}
        LIMIT 1
        """

    try:
        result = sparql_func(endpoint, query)
        bindings = result.get("results", {}).get("bindings", [])

        if bindings:
            binding = bindings[0]
            return {
                "id": entity_id.upper(),
                "type": entity_type,
                "uri": binding.get("item", binding.get("property", {})).get("value"),
                "label": binding.get("itemLabel", binding.get("propertyLabel", {})).get("value"),
            }
    except Exception:
        # Entity resolution failed - return None
        pass

    return None


def get_entity_type_uri(entity_type: str = "item", base_url: str = "http://www.wikidata.org") -> str:
    """Get the URI for an entity type.

    Args:
        entity_type: Type of entity ('item', 'property', 'lexeme', etc.).
        base_url: Base URL for the Wikibase instance.

    Returns:
        URI for the entity type.

    Examples:
        >>> get_entity_type_uri("item")
        'http://www.wikidata.org/ontology#Item'
        >>> get_entity_type_uri("property")
        'http://www.wikidata.org/ontology#Property'
    """
    base = base_url.rstrip("/")
    type_map = {
        "item": "Item",
        "property": "Property",
        "lexeme": "Lexeme",
        "form": "Form",
        "sense": "Sense",
    }
    ontology_type = type_map.get(entity_type.lower(), entity_type.capitalize())
    return f"{base}/ontology#{ontology_type}"
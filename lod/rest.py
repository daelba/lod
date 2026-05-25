"""RESTful API Client for Wikibase MediaWiki API.

This module provides an async HTTP client for direct communication with
Wikibase instances via their REST API endpoints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import httpx

from .errors import (
    AuthenticationError,
    EntityNotFoundError,
    LODError,
    NetworkError,
    RateLimitError,
    RetryConfig,
    SPARQLError,
    ValidationError,
    is_rate_limit_status,
    is_server_error_status,
)
from .validation import normalize_uri, parse_entity_uri, validate_pid, validate_qid

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_USER_AGENT = "lod-rest-client/1.0 (+https://github.com/daelba/lod)"
DEFAULT_TIMEOUT = 30.0  # seconds
DEFAULT_MAX_RETRIES = 3


@dataclass
class ActionResult:
    """Result of a Wikibase action (create, update, delete).

    Attributes:
        success: Whether the action was successful.
        entity_id: The ID of the affected entity (if applicable).
        revision_id: The revision ID of the change (if applicable).
        message: Additional information about the result.
        raw_response: The raw API response data.
    """

    success: bool
    entity_id: Optional[str] = None
    revision_id: Optional[int] = None
    message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class WikibaseRESTClient:
    """Async RESTful client for Wikibase MediaWiki API.

    This client provides methods to interact with Wikibase instances via their
    REST API, supporting operations like reading, creating, and updating entities.

    Example usage:
        >>> import asyncio
        >>> from lod.rest import WikibaseRESTClient
        >>>
        >>> async def main():
        ...     client = WikibaseRESTClient("https://www.wikidata.org")
        ...     item = await client.get_item("Q486972")
        ...     print(item["labels"]["en"])
        >>>
        >>> asyncio.run(main())

    Attributes:
        base_url: Base URL of the Wikibase instance.
        user_agent: User-Agent header for HTTP requests.
        timeout: Default timeout for requests in seconds.
        retry_config: Configuration for retry behavior.
    """

    def __init__(
        self,
        base_url: str,
        user_agent: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry_config: Optional[RetryConfig] = None,
        api_token: Optional[str] = None,
    ):
        """Initialize the REST client.

        Args:
            base_url: Base URL of the Wikibase instance (e.g., 'https://www.wikidata.org').
            user_agent: Custom User-Agent header for requests.
            timeout: Default timeout for HTTP requests in seconds.
            retry_config: Optional retry configuration. Uses DEFAULT_RETRY_CONFIG if not provided.
            api_token: Optional API token for authenticated requests (for write operations).
        """
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self._api_token = api_token
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"User-Agent": self.user_agent}
            if self._api_token:
                headers["Authorization"] = f"Bearer {self._api_token}"
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "WikibaseRESTClient":
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path (e.g., '/w/api.php').
            params: Query parameters.
            data: Form data for POST requests.
            files: Files for multipart uploads.

        Returns:
            Parsed JSON response as dictionary.

        Raises:
            NetworkError: If the request fails after all retries.
            RateLimitError: If rate limited and retry exhausted.
            AuthenticationError: If authentication fails.
        """
        url = f"{self.base_url}{endpoint}"
        client = await self._get_client()

        last_error: Optional[Exception] = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Catch network-level exceptions
                try:
                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        data=data,
                        files=files,
                    )
                except (httpx.NetworkError, httpx.ConnectError, ConnectionError, OSError) as e:
                    if attempt < self.retry_config.max_retries:
                        delay = self.retry_config.get_delay(attempt)
                        logger.warning(
                            "Network error: %s. Retrying in %.1f seconds (attempt %d/%d)",
                            str(e),
                            delay,
                            attempt + 1,
                            self.retry_config.max_retries + 1,
                        )
                        await self._safe_sleep(delay)
                        continue
                    raise NetworkError(
                        f"Network error after {attempt + 1} attempts: {e}",
                        url=url,
                        original_error=e,
                    )

                # Handle rate limiting
                if is_rate_limit_status(response.status_code):
                    retry_after = int(response.headers.get("Retry-After", 0)) or None
                    if attempt < self.retry_config.max_retries:
                        delay = self.retry_config.get_delay(attempt)
                        if retry_after:
                            delay = max(delay, retry_after)
                        logger.warning(
                            "Rate limited. Retrying in %.1f seconds (attempt %d/%d)",
                            delay,
                            attempt + 1,
                            self.retry_config.max_retries + 1,
                        )
                        await self._safe_sleep(delay)
                        continue
                    raise RateLimitError(
                        f"Rate limit exceeded for {url}", retry_after=retry_after
                    )

                # Handle server errors with retry
                if is_server_error_status(response.status_code):
                    if attempt < self.retry_config.max_retries:
                        delay = self.retry_config.get_delay(attempt)
                        logger.warning(
                            "Server error %d. Retrying in %.1f seconds (attempt %d/%d)",
                            response.status_code,
                            delay,
                            attempt + 1,
                            self.retry_config.max_retries + 1,
                        )
                        await self._safe_sleep(delay)
                        continue
                    raise NetworkError(
                        f"Server error {response.status_code} after {attempt + 1} attempts",
                        url=url,
                    )

                # Handle authentication errors
                if response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed for {url}",
                        reason="Invalid or missing credentials",
                    )

                if response.status_code == 403:
                    raise AuthenticationError(
                        f"Access denied to {url}",
                        reason="Insufficient permissions",
                    )

                # Handle entity not found
                if response.status_code == 404:
                    # Try to extract entity ID from params
                    entity_id = None
                    if params and "ids" in params:
                        entity_id = params["ids"].split(",")[0]
                    raise EntityNotFoundError(entity_id or "unknown")

                response.raise_for_status()
                return response.json()

            except httpx.RequestError as e:
                last_error = e
                if attempt < self.retry_config.max_retries:
                    if self.retry_config.should_retry_exception(e):
                        delay = self.retry_config.get_delay(attempt)
                        logger.warning(
                            "Request error: %s. Retrying in %.1f seconds (attempt %d/%d)",
                            str(e),
                            delay,
                            attempt + 1,
                            self.retry_config.max_retries + 1,
                        )
                        await self._safe_sleep(delay)
                        continue
                raise NetworkError(
                    f"Request failed: {str(e)}", url=url, original_error=e
                ) from e

            except (RateLimitError, AuthenticationError, EntityNotFoundError):
                raise

        # Should not reach here, but just in case
        raise NetworkError(
            f"Request failed after {self.retry_config.max_retries + 1} attempts",
            url=url,
            original_error=last_error,
        )

    async def _safe_sleep(self, seconds: float) -> None:
        """Sleep for given seconds, handling interruptions."""
        try:
            await self._get_client()
            import asyncio

            await asyncio.sleep(seconds)
        except Exception:
            pass  # Ignore sleep interruptions

    # ==================== READ OPERATIONS ====================

    async def get_item(self, qid: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve a Wikibase item by QID.

        Args:
            qid: The entity ID (e.g., 'Q486972').
            language: Optional language code to filter labels/descriptions.

        Returns:
            Dictionary containing item data (labels, descriptions, claims, sitelinks).

        Raises:
            ValidationError: If QID format is invalid.
            EntityNotFoundError: If item does not exist.
            NetworkError: If network request fails.
        """
        if not validate_qid(qid):
            raise ValidationError(f"Invalid QID format: {qid}", field="qid", value=qid)

        params = {
            "action": "wbgetentities",
            "ids": qid,
            "format": "json",
            "props": "labels|descriptions|claims|sitelinks|aliases",
        }

        if language:
            params["languages"] = language

        response = await self._request("GET", "/w/api.php", params=params)

        entities = response.get("entities", {})
        if not entities:
            raise EntityNotFoundError(qid, "item")

        return entities.get(qid, {}) or list(entities.values())[0]

    async def get_property(self, pid: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve a Wikibase property by PID.

        Args:
            pid: The property ID (e.g., 'P31').
            language: Optional language code to filter labels/descriptions.

        Returns:
            Dictionary containing property data.

        Raises:
            ValidationError: If PID format is invalid.
            EntityNotFoundError: If property does not exist.
        """
        if not validate_pid(pid):
            raise ValidationError(f"Invalid PID format: {pid}", field="pid", value=pid)

        params = {
            "action": "wbgetentities",
            "ids": pid,
            "format": "json",
            "props": "labels|descriptions|claims|datatype",
        }

        if language:
            params["languages"] = language

        response = await self._request("GET", "/w/api.php", params=params)

        entities = response.get("entities", {})
        if not entities:
            raise EntityNotFoundError(pid, "property")

        return entities.get(pid, {}) or list(entities.values())[0]

    async def get_entity(
        self, entity_id: str, language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve any entity (item or property) by ID.

        Args:
            entity_id: The entity ID (QID or PID).
            language: Optional language code to filter labels/descriptions.

        Returns:
            Dictionary containing entity data.
        """
        if entity_id.upper().startswith("Q"):
            return await self.get_item(entity_id, language)
        elif entity_id.upper().startswith("P"):
            return await self.get_property(entity_id, language)
        else:
            raise ValidationError(
                f"Unknown entity type for ID: {entity_id}", field="entity_id", value=entity_id
            )

    async def search_entities(
        self,
        search: str,
        language: str = "cs",
        limit: int = 10,
        entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for entities by text.

        Args:
            search: Search query string.
            language: Language code for search (default: 'cs').
            limit: Maximum number of results (default: 10).
            entity_type: Filter by type ('item' or 'property'), or None for both.

        Returns:
            List of matching entities with basic info (id, label, description).
        """
        params = {
            "action": "wbsearchentities",
            "search": search,
            "language": language,
            "format": "json",
            "limit": min(limit, 50),  # API max is typically 50
        }

        if entity_type:
            params["type"] = entity_type

        response = await self._request("GET", "/w/api.php", params=params)
        return response.get("search", [])

    # ==================== WRITE OPERATIONS ====================

    async def create_item(
        self,
        label: str,
        description: Optional[str] = None,
        language: str = "cs",
        claims: Optional[Dict[str, Any]] = None,
    ) -> ActionResult:
        """Create a new item.

        Args:
            label: The label for the new item.
            description: Optional description.
            language: Language code for label/description (default: 'cs').
            claims: Optional initial claims as dict {property_id: value}.

        Returns:
            ActionResult with the new entity ID.

        Raises:
            AuthenticationError: If not authenticated for write operations.
        """
        data = {
            "action": "wbcreateentity",
            "format": "json",
            "new": "item",
            f"data[{language}]": label,
        }

        if description:
            data[f"data[{language}][description]"] = description

        # Add token for write operation
        if self._api_token:
            data["token"] = self._api_token

        response = await self._request("POST", "/w/api.php", data=data)

        entity = response.get("entity", {})
        entity_id = entity.get("id")

        # Add initial claims if provided
        if claims and entity_id:
            for prop_id, value in claims.items():
                await self.set_claim(entity_id, prop_id, value)

        return ActionResult(
            success=True,
            entity_id=entity_id,
            revision_id=entity.get("lastrevid"),
            message=f"Created item {entity_id}",
            raw_response=response,
        )

    async def create_property(
        self,
        label: str,
        datatype: str,
        description: Optional[str] = None,
        language: str = "cs",
    ) -> ActionResult:
        """Create a new property.

        Args:
            label: The label for the new property.
            datatype: The property datatype (e.g., 'string', 'wikibase-item', 'quantity').
            description: Optional description.
            language: Language code for label/description (default: 'cs').

        Returns:
            ActionResult with the new property ID.
        """
        valid_datatypes = [
            "commonsMedia",
            "external-id",
            "geo-shape",
            "globe-coordinate",
            "math",
            "musical-notation",
            "property",
            "quantity",
            "string",
            "tabular-data",
            "time",
            "url",
            "wikibase-form",
            "wikibase-item",
            "wikibase-lexeme",
            "wikibase-property",
            "wikibase-sense",
        ]

        if datatype not in valid_datatypes:
            raise ValidationError(
                f"Invalid datatype: {datatype}", field="datatype", value=datatype
            )

        data = {
            "action": "wbcreateentity",
            "format": "json",
            "new": "property",
            f"data[{language}]": label,
            "datatype": datatype,
        }

        if description:
            data[f"data[{language}][description]"] = description

        if self._api_token:
            data["token"] = self._api_token

        response = await self._request("POST", "/w/api.php", data=data)

        entity = response.get("entity", {})
        return ActionResult(
            success=True,
            entity_id=entity.get("id"),
            revision_id=entity.get("lastrevid"),
            message=f"Created property {entity.get('id')}",
            raw_response=response,
        )

    async def set_label(
        self, entity_id: str, value: str, language: str = "cs"
    ) -> ActionResult:
        """Set or update a label on an entity.

        Args:
            entity_id: The entity ID (QID or PID).
            value: The label text.
            language: Language code (default: 'cs').

        Returns:
            ActionResult indicating success.
        """
        if not validate_qid(entity_id) and not validate_pid(entity_id):
            raise ValidationError(
                f"Invalid entity ID: {entity_id}", field="entity_id", value=entity_id
            )

        data = {
            "action": "wbsetlabel",
            "format": "json",
            "id": entity_id,
            f"value": value,
            "language": language,
        }

        if self._api_token:
            data["token"] = self._api_token

        response = await self._request("POST", "/w/api.php", data=data)

        return ActionResult(
            success=True,
            entity_id=entity_id,
            message=f"Set label on {entity_id}",
            raw_response=response,
        )

    async def set_description(
        self, entity_id: str, value: str, language: str = "cs"
    ) -> ActionResult:
        """Set or update a description on an entity.

        Args:
            entity_id: The entity ID (QID or PID).
            value: The description text.
            language: Language code (default: 'cs').

        Returns:
            ActionResult indicating success.
        """
        if not validate_qid(entity_id) and not validate_pid(entity_id):
            raise ValidationError(
                f"Invalid entity ID: {entity_id}", field="entity_id", value=entity_id
            )

        data = {
            "action": "wbsetdescription",
            "format": "json",
            "id": entity_id,
            "value": value,
            "language": language,
        }

        if self._api_token:
            data["token"] = self._api_token

        response = await self._request("POST", "/w/api.php", data=data)

        return ActionResult(
            success=True,
            entity_id=entity_id,
            message=f"Set description on {entity_id}",
            raw_response=response,
        )

    async def set_claim(
        self,
        entity_id: str,
        property_id: str,
        value: Any,
        snak_type: str = "value",
    ) -> ActionResult:
        """Add or update a claim (property statement) on an entity.

        Args:
            entity_id: The entity ID (QID or PID).
            property_id: The property ID (PID).
            value: The value for the claim. Can be string, number, QID, or dict.
            snak_type: Type of snak ('value', 'somevalue', 'novalue').

        Returns:
            ActionResult indicating success.

        Note:
            For complex values, use the datavalue format:
            {
                "type": "wikibase-entityid",
                "value": {"entity-type": "item", "numeric-id": 123}
            }
        """
        if not validate_qid(entity_id) and not validate_pid(entity_id):
            raise ValidationError(
                f"Invalid entity ID: {entity_id}", field="entity_id", value=entity_id
            )

        if not validate_pid(property_id):
            raise ValidationError(
                f"Invalid property ID: {property_id}", field="property_id", value=property_id
            )

        # Format the value based on type
        if isinstance(value, dict):
            # Already formatted datavalue
            datavalue = value
        elif isinstance(value, str) and value.startswith("Q"):
            # Wikibase entity reference
            numeric_id = value[1:]
            datavalue = {
                "type": "wikibase-entityid",
                "value": {"entity-type": "item", "numeric-id": int(numeric_id)},
            }
        elif isinstance(value, str):
            # String value
            datavalue = {"type": "string", "value": value}
        elif isinstance(value, (int, float)):
            # Quantity value
            datavalue = {
                "type": "quantity",
                "value": {"amount": f"+{value}", "unit": "1"},
            }
        else:
            # Default to string
            datavalue = {"type": "string", "value": str(value)}

        data = {
            "action": "wbsetclaim",
            "format": "json",
            "id": entity_id,
            "claim": f"{property_id}:{snak_type}",
            "value": str(datavalue),
        }

        if self._api_token:
            data["token"] = self._api_token

        response = await self._request("POST", "/w/api.php", data=data)

        return ActionResult(
            success=True,
            entity_id=entity_id,
            message=f"Set claim {property_id} on {entity_id}",
            raw_response=response,
        )

    async def delete_entity(self, entity_id: str) -> ActionResult:
        """Delete an entity (requires admin rights).

        Args:
            entity_id: The entity ID to delete.

        Returns:
            ActionResult indicating success or failure.
        """
        data = {
            "action": "wbdeleteentity",
            "format": "json",
            "id": entity_id,
        }

        if self._api_token:
            data["token"] = self._api_token

        response = await self._request("POST", "/w/api.php", data=data)

        return ActionResult(
            success=response.get("success") == 1,
            entity_id=entity_id,
            message=f"Deleted entity {entity_id}" if response.get("success") else "Delete failed",
            raw_response=response,
        )

    # ==================== UTILITY METHODS ====================

    async def get_edit_token(self) -> Optional[str]:
        """Fetch an edit token for write operations.

        Returns:
            The edit token string, or None if not available.
        """
        params = {
            "action": "query",
            "format": "json",
            "meta": "tokens",
            "type": "csrf",
        }

        response = await self._request("GET", "/w/api.php", params=params)
        return response.get("query", {}).get("tokens", {}).get("csrftoken")

    def set_api_token(self, token: str) -> None:
        """Set the API token for authenticated requests.

        Args:
            token: The API/edit token for write operations.
        """
        self._api_token = token

    def get_entity_uri(self, entity_id: str) -> str:
        """Get the full URI for an entity.

        Args:
            entity_id: The entity ID.

        Returns:
            Full URI like 'http://www.wikidata.org/entity/Q123'.
        """
        return normalize_uri(entity_id, base_url=self.base_url)


# Convenience function for simple use cases
async def quick_get_item(base_url: str, qid: str, language: Optional[str] = None) -> Dict[str, Any]:
    """Quick one-liner to get an item.

    Args:
        base_url: Base URL of Wikibase instance.
        qid: Entity ID.
        language: Optional language filter.

    Returns:
        Item data dictionary.

    Example:
        >>> item = await quick_get_item("https://www.wikidata.org", "Q486972")
    """
    async with WikibaseRESTClient(base_url) as client:
        return await client.get_item(qid, language)
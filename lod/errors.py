"""Error handling and retry strategies for LOD library.

This module provides custom exceptions and retry configuration for robust
Wikibase/SPARQL communication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Type


class LODError(Exception):
    """Base exception for LOD library."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v!r}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class SPARQLError(LODError):
    """SPARQL query execution error."""

    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
        endpoint: Optional[str] = None,
    ):
        details = {}
        if query is not None:
            details["query"] = query[:200] + "..." if len(query) > 200 else query
        if endpoint is not None:
            details["endpoint"] = endpoint
        super().__init__(message, details)
        self.query = query
        self.endpoint = endpoint


class RateLimitError(LODError):
    """Rate limit exceeded error.

    Attributes:
        retry_after: Seconds to wait before retrying (if provided by server).
    """

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message, {"retry_after": retry_after} if retry_after else {})
        self.retry_after = retry_after


class AuthenticationError(LODError):
    """Authentication failed error."""

    def __init__(self, message: str, reason: Optional[str] = None):
        details = {"reason": reason} if reason else {}
        super().__init__(message, details)
        self.reason = reason


class EntityNotFoundError(LODError):
    """Requested entity was not found.

    Raised when an entity ID (QID/PID) does not exist in the Wikibase instance.
    """

    def __init__(self, entity_id: str, entity_type: Optional[str] = None):
        details = {"entity_id": entity_id}
        if entity_type:
            details["entity_type"] = entity_type
        super().__init__(f"Entity {entity_id} not found", details)
        self.entity_id = entity_id
        self.entity_type = entity_type


class ValidationError(LODError):
    """Validation error for entity IDs or data.

    Raised when entity ID format is invalid or data validation fails.
    """

    def __init__(self, message: str, field: Optional[str] = None, value: Optional[str] = None):
        details = {}
        if field:
            details["field"] = field
        if value:
            details["value"] = value[:100] + "..." if len(value) > 100 else value
        super().__init__(message, details)
        self.field = field
        self.value = value


class NetworkError(LODError):
    """Network communication error.

    Raised when network requests fail due to connection issues, timeouts, etc.
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if url:
            details["url"] = url
        if original_error:
            details["original_error"] = type(original_error).__name__
        super().__init__(message, details)
        self.url = url
        self.original_error = original_error


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 3).
        backoff_factor: Multiplier for delay between retries (default: 2.0).
        status_codes: HTTP status codes that trigger a retry (default: 429, 500, 502, 503, 504).
        exceptions: Exception types that trigger a retry.
        retry_delay_seconds: Initial delay before first retry (default: 1.0).
        max_delay_seconds: Maximum delay between retries (default: 60.0).
    """

    max_retries: int = 3
    backoff_factor: float = 2.0
    status_codes: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    exceptions: List[Type[Exception]] = field(
        default_factory=lambda: [ConnectionError, TimeoutError, OSError]
    )
    retry_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number using exponential backoff.

        Args:
            attempt: The attempt number (0-indexed).

        Returns:
            Delay in seconds, capped at max_delay_seconds.
        """
        delay = self.retry_delay_seconds * (self.backoff_factor**attempt)
        return min(delay, self.max_delay_seconds)

    def should_retry_status(self, status_code: int) -> bool:
        """Check if given status code should trigger a retry.

        Args:
            status_code: HTTP status code.

        Returns:
            True if status code is in retry list.
        """
        return status_code in self.status_codes

    def should_retry_exception(self, exception: Exception) -> bool:
        """Check if given exception type should trigger a retry.

        Args:
            exception: The exception instance.

        Returns:
            True if exception type is in retry list.
        """
        return any(isinstance(exception, exc_type) for exc_type in self.exceptions)


# Default retry configuration
DEFAULT_RETRY_CONFIG = RetryConfig()


def is_rate_limit_status(status_code: int) -> bool:
    """Check if HTTP status code indicates rate limiting.

    Args:
        status_code: HTTP status code.

    Returns:
        True if status is 429 (Too Many Requests).
    """
    return status_code == 429


def is_server_error_status(status_code: int) -> bool:
    """Check if HTTP status code indicates a server error.

    Args:
        status_code: HTTP status code.

    Returns:
        True if status is 5xx.
    """
    return 500 <= status_code < 600
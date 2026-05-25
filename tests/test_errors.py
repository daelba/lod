"""Tests for lod.errors module."""

import pytest

from lod.errors import (
    LODError,
    SPARQLError,
    RateLimitError,
    AuthenticationError,
    EntityNotFoundError,
    ValidationError,
    NetworkError,
    RetryConfig,
    DEFAULT_RETRY_CONFIG,
    is_rate_limit_status,
    is_server_error_status,
)


class TestLODError:
    """Tests for LODError base exception."""

    def test_basic_error(self):
        """Test basic error creation and string representation."""
        error = LODError("Test error message")
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.details == {}

    def test_error_with_details(self):
        """Test error with additional details."""
        error = LODError("Error occurred", details={"field": "value", "count": 42})
        assert "field='value'" in str(error)
        assert "count=42" in str(error)


class TestSPARQLError:
    """Tests for SPARQLError exception."""

    def test_basic_sparql_error(self):
        """Test basic SPARQL error."""
        error = SPARQLError("Query failed")
        assert "Query failed" in str(error)
        assert error.query is None
        assert error.endpoint is None

    def test_sparql_error_with_context(self):
        """Test SPARQL error with query and endpoint context."""
        query = "SELECT * WHERE { ?s ?p ?o }"
        endpoint = "https://query.wikidata.org/sparql"
        error = SPARQLError("Query timeout", query=query, endpoint=endpoint)
        
        assert error.query == query
        assert error.endpoint == endpoint
        assert endpoint in str(error)

    def test_sparql_error_truncates_long_query(self):
        """Test that long queries are truncated in details."""
        long_query = "SELECT * WHERE { " + "?s ?p ?o . " * 100 + "}"
        error = SPARQLError("Query failed", query=long_query)
        
        assert len(error.details.get("query", "")) <= 203  # 200 + "..."


class TestRateLimitError:
    """Tests for RateLimitError exception."""

    def test_basic_rate_limit(self):
        """Test basic rate limit error."""
        error = RateLimitError("Rate limit exceeded")
        assert error.retry_after is None
        assert "Rate limit exceeded" in str(error)

    def test_rate_limit_with_retry_after(self):
        """Test rate limit error with retry-after value."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)
        assert error.retry_after == 60
        assert "retry_after=60" in str(error)


class TestAuthenticationError:
    """Tests for AuthenticationError exception."""

    def test_basic_auth_error(self):
        """Test basic authentication error."""
        error = AuthenticationError("Authentication failed")
        assert error.reason is None
        assert "Authentication failed" in str(error)

    def test_auth_error_with_reason(self):
        """Test authentication error with reason."""
        error = AuthenticationError("Access denied", reason="Invalid token")
        assert error.reason == "Invalid token"
        assert "reason='Invalid token'" in str(error)


class TestEntityNotFoundError:
    """Tests for EntityNotFoundError exception."""

    def test_basic_entity_not_found(self):
        """Test basic entity not found error."""
        error = EntityNotFoundError("Q123")
        assert error.entity_id == "Q123"
        assert error.entity_type is None
        assert "Q123" in str(error)

    def test_entity_not_found_with_type(self):
        """Test entity not found error with type."""
        error = EntityNotFoundError("P31", entity_type="property")
        assert error.entity_id == "P31"
        assert error.entity_type == "property"
        assert "property" in str(error)


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_basic_validation_error(self):
        """Test basic validation error."""
        error = ValidationError("Invalid format")
        assert error.field is None
        assert error.value is None
        assert "Invalid format" in str(error)

    def test_validation_error_with_field(self):
        """Test validation error with field name."""
        error = ValidationError("Invalid value", field="entity_id")
        assert error.field == "entity_id"
        assert "field='entity_id'" in str(error)

    def test_validation_error_with_value(self):
        """Test validation error with invalid value."""
        error = ValidationError("Invalid format", field="qid", value="Q123abc")
        assert error.field == "qid"
        assert "Q123abc" in str(error)

    def test_validation_error_truncates_long_value(self):
        """Test that long values are truncated."""
        long_value = "x" * 200
        error = ValidationError("Invalid", field="data", value=long_value)
        value_str = str(error)
        assert len(value_str) < 200  # Truncated with "..."


class TestNetworkError:
    """Tests for NetworkError exception."""

    def test_basic_network_error(self):
        """Test basic network error."""
        error = NetworkError("Connection failed")
        assert error.url is None
        assert error.original_error is None
        assert "Connection failed" in str(error)

    def test_network_error_with_url(self):
        """Test network error with URL."""
        error = NetworkError("Timeout", url="https://example.com/api")
        assert error.url == "https://example.com/api"
        assert "url=" in str(error)

    def test_network_error_with_original(self):
        """Test network error with original exception."""
        original = ConnectionError("Connection refused")
        error = NetworkError("Request failed", original_error=original)
        assert error.original_error is original
        assert "ConnectionError" in str(error)


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_config(self):
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.backoff_factor == 2.0
        assert config.retry_delay_seconds == 1.0
        assert config.max_delay_seconds == 60.0
        assert 429 in config.status_codes
        assert 500 in config.status_codes

    def test_custom_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_retries=5,
            backoff_factor=3.0,
            retry_delay_seconds=2.0,
            max_delay_seconds=120.0,
        )
        assert config.max_retries == 5
        assert config.backoff_factor == 3.0

    def test_get_delay_exponential(self):
        """Test exponential backoff delay calculation."""
        config = RetryConfig(retry_delay_seconds=1.0, backoff_factor=2.0, max_delay_seconds=60.0)
        
        assert config.get_delay(0) == 1.0
        assert config.get_delay(1) == 2.0
        assert config.get_delay(2) == 4.0
        assert config.get_delay(3) == 8.0

    def test_get_delay_capped(self):
        """Test that delay is capped at max_delay_seconds."""
        config = RetryConfig(retry_delay_seconds=1.0, backoff_factor=2.0, max_delay_seconds=10.0)
        
        # After several attempts, delay should be capped
        assert config.get_delay(10) == 10.0
        assert config.get_delay(20) == 10.0

    def test_should_retry_status(self):
        """Test status code retry check."""
        config = RetryConfig(status_codes=[429, 500, 503])
        
        assert config.should_retry_status(429) is True
        assert config.should_retry_status(500) is True
        assert config.should_retry_status(503) is True
        assert config.should_retry_status(404) is False
        assert config.should_retry_status(200) is False

    def test_should_retry_exception(self):
        """Test exception type retry check."""
        config = RetryConfig(exceptions=[ConnectionError, TimeoutError])
        
        assert config.should_retry_exception(ConnectionError()) is True
        assert config.should_retry_exception(TimeoutError()) is True
        assert config.should_retry_exception(ValueError()) is False


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_is_rate_limit_status(self):
        """Test rate limit status check."""
        assert is_rate_limit_status(429) is True
        assert is_rate_limit_status(200) is False
        assert is_rate_limit_status(500) is False

    def test_is_server_error_status(self):
        """Test server error status check."""
        assert is_server_error_status(500) is True
        assert is_server_error_status(502) is True
        assert is_server_error_status(503) is True
        assert is_server_error_status(504) is True
        assert is_server_error_status(429) is False
        assert is_server_error_status(404) is False
        assert is_server_error_status(200) is False


class TestDefaultRetryConfig:
    """Tests for DEFAULT_RETRY_CONFIG."""

    def test_default_config_exists(self):
        """Test that default retry config is available."""
        assert DEFAULT_RETRY_CONFIG is not None
        assert isinstance(DEFAULT_RETRY_CONFIG, RetryConfig)

    def test_default_config_values(self):
        """Test default config has expected values."""
        assert DEFAULT_RETRY_CONFIG.max_retries == 3
        assert DEFAULT_RETRY_CONFIG.backoff_factor == 2.0
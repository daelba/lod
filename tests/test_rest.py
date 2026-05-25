"""Tests for lod.rest module.

Note: These tests use mocking to avoid making real HTTP requests.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from lod.errors import (
    ValidationError,
    EntityNotFoundError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    RetryConfig,
)


@pytest.fixture
def mock_httpx_response():
    """Create a mock httpx response."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json.return_value = {"entities": {"Q123": {"id": "Q123", "labels": {}}}}
    response.raise_for_status = MagicMock()
    return response


@pytest_asyncio.fixture
async def mock_async_client():
    """Create a mock async HTTP client."""
    with patch("lod.rest.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"entities": {"Q123": {"id": "Q123"}}}
        mock_response.raise_for_status = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        mock_client_class.return_value = mock_client
        yield mock_client


class TestWikibaseRESTClientInit:
    """Tests for WikibaseRESTClient initialization."""

    def test_default_initialization(self):
        """Test default initialization values."""
        from lod.rest import WikibaseRESTClient, DEFAULT_USER_AGENT, DEFAULT_TIMEOUT
        
        client = WikibaseRESTClient("https://www.wikidata.org")
        
        assert client.base_url == "https://www.wikidata.org"
        assert client.user_agent == DEFAULT_USER_AGENT
        assert client.timeout == DEFAULT_TIMEOUT
        assert client._api_token is None

    def test_custom_initialization(self):
        """Test custom initialization values."""
        from lod.rest import WikibaseRESTClient
        
        client = WikibaseRESTClient(
            base_url="https://custom.wikibase.cloud",
            user_agent="CustomAgent/1.0",
            timeout=60.0,
            api_token="test_token",
        )
        
        assert client.base_url == "https://custom.wikibase.cloud"
        assert client.user_agent == "CustomAgent/1.0"
        assert client.timeout == 60.0
        assert client._api_token == "test_token"

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slash is removed from base URL."""
        from lod.rest import WikibaseRESTClient
        
        client = WikibaseRESTClient("https://www.wikidata.org/")
        assert client.base_url == "https://www.wikidata.org"

    def test_custom_retry_config(self):
        """Test custom retry configuration."""
        from lod.rest import WikibaseRESTClient
        
        custom_retry = RetryConfig(max_retries=10, backoff_factor=3.0)
        client = WikibaseRESTClient(
            "https://www.wikidata.org",
            retry_config=custom_retry,
        )
        
        assert client.retry_config.max_retries == 10
        assert client.retry_config.backoff_factor == 3.0


@pytest.mark.asyncio
class TestWikibaseRESTClientAsync:
    """Async tests for WikibaseRESTClient."""

    async def test_context_manager(self, mock_async_client):
        """Test async context manager."""
        from lod.rest import WikibaseRESTClient
        
        async with WikibaseRESTClient("https://www.wikidata.org") as client:
            assert client._client is not None
        
        mock_async_client.aclose.assert_called()

    async def test_close_method(self, mock_async_client):
        """Test close method."""
        from lod.rest import WikibaseRESTClient
        
        client = WikibaseRESTClient("https://www.wikidata.org")
        await client._get_client()
        await client.close()
        
        mock_async_client.aclose.assert_called()

    async def test_get_item_valid_qid(self, mock_async_client):
        """Test get_item with valid QID."""
        from lod.rest import WikibaseRESTClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "entities": {
                "Q486972": {
                    "id": "Q486972",
                    "type": "item",
                    "labels": {"en": {"language": "en", "value": "Test"}}
                }
            }
        }
        mock_async_client.request = AsyncMock(return_value=mock_response)
        
        async with WikibaseRESTClient("https://www.wikidata.org") as client:
            result = await client.get_item("Q486972")
            
            assert result["id"] == "Q486972"
            mock_async_client.request.assert_called()

    async def test_get_item_invalid_qid(self):
        """Test get_item with invalid QID."""
        from lod.rest import WikibaseRESTClient
        
        client = WikibaseRESTClient("https://www.wikidata.org")
        
        with pytest.raises(ValidationError):
            await client.get_item("invalid")

    async def test_get_property_valid_pid(self, mock_async_client):
        """Test get_property with valid PID."""
        from lod.rest import WikibaseRESTClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "entities": {
                "P31": {
                    "id": "P31",
                    "type": "property",
                    "datatype": "wikibase-item"
                }
            }
        }
        mock_async_client.request = AsyncMock(return_value=mock_response)
        
        async with WikibaseRESTClient("https://www.wikidata.org") as client:
            result = await client.get_property("P31")
            
            assert result["id"] == "P31"

    async def test_get_property_invalid_pid(self):
        """Test get_property with invalid PID."""
        from lod.rest import WikibaseRESTClient
        
        client = WikibaseRESTClient("https://www.wikidata.org")
        
        with pytest.raises(ValidationError):
            await client.get_property("invalid")

    async def test_get_entity_item(self, mock_async_client):
        """Test get_entity with item ID."""
        from lod.rest import WikibaseRESTClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "entities": {"Q123": {"id": "Q123", "type": "item"}}
        }
        mock_async_client.request = AsyncMock(return_value=mock_response)
        
        async with WikibaseRESTClient("https://www.wikidata.org") as client:
            result = await client.get_entity("Q123")
            assert result["type"] == "item"

    async def test_get_entity_property(self, mock_async_client):
        """Test get_entity with property ID."""
        from lod.rest import WikibaseRESTClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "entities": {"P31": {"id": "P31", "type": "property"}}
        }
        mock_async_client.request = AsyncMock(return_value=mock_response)
        
        async with WikibaseRESTClient("https://www.wikidata.org") as client:
            result = await client.get_entity("P31")
            assert result["type"] == "property"

    async def test_search_entities(self, mock_async_client):
        """Test search_entities."""
        from lod.rest import WikibaseRESTClient
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "search": [
                {"id": "Q123", "label": "Test", "description": "Test description"}
            ]
        }
        mock_async_client.request = AsyncMock(return_value=mock_response)
        
        async with WikibaseRESTClient("https://www.wikidata.org") as client:
            results = await client.search_entities("test", language="cs", limit=5)
            
            assert len(results) == 1
            assert results[0]["id"] == "Q123"

    async def test_rate_limit_error(self):
        """Test rate limit error handling."""
        from lod.rest import WikibaseRESTClient
        
        with patch("lod.rest.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "60"}
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            mock_client_class.return_value = mock_client
            
            client = WikibaseRESTClient(
                "https://www.wikidata.org",
                retry_config=RetryConfig(max_retries=0),
            )
            
            with pytest.raises(RateLimitError) as exc_info:
                await client.get_item("Q123")
            
            assert exc_info.value.retry_after == 60

    async def test_authentication_error_401(self):
        """Test 401 authentication error."""
        from lod.rest import WikibaseRESTClient
        
        with patch("lod.rest.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            mock_client_class.return_value = mock_client
            
            client = WikibaseRESTClient(
                "https://www.wikidata.org",
                retry_config=RetryConfig(max_retries=0),
            )
            
            with pytest.raises(AuthenticationError):
                await client.get_item("Q123")

    async def test_entity_not_found_404(self):
        """Test 404 entity not found error."""
        from lod.rest import WikibaseRESTClient
        
        with patch("lod.rest.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            mock_client_class.return_value = mock_client
            
            client = WikibaseRESTClient(
                "https://www.wikidata.org",
                retry_config=RetryConfig(max_retries=0),
            )
            
            with pytest.raises(EntityNotFoundError):
                await client.get_item("Q999999999")

    async def test_network_error(self):
        """Test network error handling."""
        from lod.rest import WikibaseRESTClient
        import httpx
        
        with patch("lod.rest.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            # Use httpx.NetworkError which is caught by the retry logic
            mock_client.request = AsyncMock(side_effect=httpx.NetworkError("Connection refused"))
            mock_client.is_closed = False
            mock_client_class.return_value = mock_client
            
            client = WikibaseRESTClient(
                "https://www.wikidata.org",
                retry_config=RetryConfig(max_retries=0),
            )
            
            with pytest.raises(NetworkError):
                await client.get_item("Q123")

    async def test_set_api_token(self):
        """Test setting API token."""
        from lod.rest import WikibaseRESTClient
        
        client = WikibaseRESTClient("https://www.wikidata.org")
        assert client._api_token is None
        
        client.set_api_token("new_token")
        assert client._api_token == "new_token"

    async def test_get_entity_uri(self):
        """Test get_entity_uri method."""
        from lod.rest import WikibaseRESTClient
        
        client = WikibaseRESTClient("https://www.wikidata.org")
        uri = client.get_entity_uri("Q123")
        
        # Should use normalize_uri from validation module
        assert "Q123" in uri


class TestActionResult:
    """Tests for ActionResult dataclass."""

    def test_basic_success(self):
        """Test basic success result."""
        from lod.rest import ActionResult
        
        result = ActionResult(success=True)
        assert result.success is True
        assert result.entity_id is None
        assert result.revision_id is None
        assert result.message is None

    def test_with_entity_info(self):
        """Test result with entity information."""
        from lod.rest import ActionResult
        
        result = ActionResult(
            success=True,
            entity_id="Q123",
            revision_id=12345,
            message="Created successfully",
        )
        
        assert result.success is True
        assert result.entity_id == "Q123"
        assert result.revision_id == 12345
        assert result.message == "Created successfully"


class TestQuickGetItem:
    """Tests for quick_get_item convenience function."""

    @pytest.mark.asyncio
    async def test_quick_get_item(self):
        """Test quick_get_item function."""
        from lod.rest import quick_get_item
        
        with patch("lod.rest.WikibaseRESTClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get_item = AsyncMock(return_value={"id": "Q123"})
            mock_client_class.return_value = mock_client
            
            result = await quick_get_item("https://www.wikidata.org", "Q123")
            
            assert result["id"] == "Q123"
            mock_client.get_item.assert_called_once_with("Q123", None)
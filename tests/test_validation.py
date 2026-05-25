"""Tests for lod.validation module."""

import pytest

from lod.errors import ValidationError
from lod.validation import (
    validate_qid,
    validate_pid,
    validate_entity_id,
    parse_entity_uri,
    normalize_uri,
    extract_entity_id,
    get_entity_type_uri,
)


class TestValidateQid:
    """Tests for validate_qid function."""

    def test_valid_qids(self):
        """Test valid QID formats."""
        assert validate_qid("Q1") is True
        assert validate_qid("Q123") is True
        assert validate_qid("Q486972") is True
        assert validate_qid("Q999999999") is True

    def test_valid_qids_lowercase(self):
        """Test valid QID formats (lowercase)."""
        assert validate_qid("q1") is True
        assert validate_qid("q123") is True
        assert validate_qid("q486972") is True

    def test_invalid_qids(self):
        """Test invalid QID formats."""
        assert validate_qid("P31") is False
        assert validate_qid("Q") is False
        assert validate_qid("Qabc") is False
        assert validate_qid("123") is False
        assert validate_qid("") is False
        assert validate_qid("Q123P") is False

    def test_non_string_input(self):
        """Test non-string input."""
        assert validate_qid(None) is False
        assert validate_qid(123) is False
        assert validate_qid([]) is False
        assert validate_qid({}) is False


class TestValidatePid:
    """Tests for validate_pid function."""

    def test_valid_pids(self):
        """Test valid PID formats."""
        assert validate_pid("P1") is True
        assert validate_pid("P31") is True
        assert validate_pid("P8") is True
        assert validate_pid("P999999999") is True

    def test_valid_pids_lowercase(self):
        """Test valid PID formats (lowercase)."""
        assert validate_pid("p1") is True
        assert validate_pid("p31") is True
        assert validate_pid("p8") is True

    def test_invalid_pids(self):
        """Test invalid PID formats."""
        assert validate_pid("Q123") is False
        assert validate_pid("P") is False
        assert validate_pid("Pabc") is False
        assert validate_pid("123") is False
        assert validate_pid("") is False
        assert validate_pid("P123Q") is False

    def test_non_string_input(self):
        """Test non-string input."""
        assert validate_pid(None) is False
        assert validate_pid(123) is False
        assert validate_pid([]) is False


class TestValidateEntityId:
    """Tests for validate_entity_id function."""

    def test_valid_item(self):
        """Test valid item entity."""
        is_valid, entity_type = validate_entity_id("Q123")
        assert is_valid is True
        assert entity_type == "item"

    def test_valid_property(self):
        """Test valid property entity."""
        is_valid, entity_type = validate_entity_id("P31")
        assert is_valid is True
        assert entity_type == "property"

    def test_invalid_entity(self):
        """Test invalid entity."""
        is_valid, entity_type = validate_entity_id("invalid")
        assert is_valid is False
        assert entity_type is None

    def test_lowercase_entity(self):
        """Test lowercase entity ID."""
        is_valid, entity_type = validate_entity_id("q123")
        assert is_valid is True
        assert entity_type == "item"

    def test_non_string_input(self):
        """Test non-string input."""
        is_valid, entity_type = validate_entity_id(None)
        assert is_valid is False
        assert entity_type is None


class TestParseEntityUri:
    """Tests for parse_entity_uri function."""

    def test_wikidata_entity_uri(self):
        """Test parsing Wikidata entity URI."""
        entity_type, entity_id = parse_entity_uri("http://www.wikidata.org/entity/Q486972")
        assert entity_type == "Q"
        assert entity_id == "Q486972"

    def test_wikidata_property_uri(self):
        """Test parsing Wikidata property URI."""
        entity_type, entity_id = parse_entity_uri("http://www.wikidata.org/prop/direct/P31")
        assert entity_type == "P"
        assert entity_id == "P31"

    def test_https_uri(self):
        """Test parsing HTTPS URI."""
        entity_type, entity_id = parse_entity_uri("https://query.wikidata.org/entity/Q123")
        assert entity_type == "Q"
        assert entity_id == "Q123"

    def test_wikibase_cloud_uri(self):
        """Test parsing Wikibase.cloud URI."""
        entity_type, entity_id = parse_entity_uri("https://retrobi.wikibase.cloud/entity/Q1")
        assert entity_type == "Q"
        assert entity_id == "Q1"

    def test_invalid_uri_raises_error(self):
        """Test invalid URI raises ValidationError."""
        with pytest.raises(ValidationError):
            parse_entity_uri("invalid-uri")

    def test_non_string_raises_error(self):
        """Test non-string raises ValidationError."""
        with pytest.raises(ValidationError):
            parse_entity_uri(None)

    def test_empty_path_raises_error(self):
        """Test empty path raises ValidationError."""
        with pytest.raises(ValidationError):
            parse_entity_uri("http://example.com/")


class TestNormalizeUri:
    """Tests for normalize_uri function."""

    def test_wikidata_item(self):
        """Test normalizing Wikidata item."""
        uri = normalize_uri("Q486972")
        assert uri == "http://www.wikidata.org/entity/Q486972"

    def test_wikidata_property(self):
        """Test normalizing Wikidata property."""
        uri = normalize_uri("P31")
        assert uri == "http://www.wikidata.org/prop/direct/P31"

    def test_lowercase_entity(self):
        """Test normalizing lowercase entity ID."""
        uri = normalize_uri("q123")
        assert uri == "http://www.wikidata.org/entity/Q123"

    def test_custom_project_code(self):
        """Test custom project code."""
        uri = normalize_uri("Q123", project_code="wikibase")
        assert uri == "http://wikibase.wikibase.cloud/entity/Q123"

    def test_custom_base_url(self):
        """Test custom base URL."""
        uri = normalize_uri("Q123", base_url="https://my.wikibase.cloud")
        assert uri == "https://my.wikibase.cloud/entity/Q123"

    def test_invalid_entity_id_raises_error(self):
        """Test invalid entity ID raises ValidationError."""
        with pytest.raises(ValidationError):
            normalize_uri("invalid")

    def test_non_string_raises_error(self):
        """Test non-string raises ValidationError."""
        with pytest.raises(ValidationError):
            normalize_uri(None)


class TestExtractEntityId:
    """Tests for extract_entity_id function."""

    def test_plain_entity_id(self):
        """Test extracting plain entity ID."""
        assert extract_entity_id("Q486972") == "Q486972"
        assert extract_entity_id("q123") == "Q123"

    def test_full_uri(self):
        """Test extracting from full URI."""
        result = extract_entity_id("http://www.wikidata.org/entity/Q486972")
        assert result == "Q486972"

    def test_with_prefix(self):
        """Test extracting with prefix."""
        assert extract_entity_id("wd:Q486972") == "Q486972"
        assert extract_entity_id("wdt:P31") == "P31"

    def test_curly_braces(self):
        """Test extracting from curly braces."""
        assert extract_entity_id("{Q123}") == "Q123"
        assert extract_entity_id("{Q486972}") == "Q486972"

    def test_square_brackets(self):
        """Test extracting from square brackets."""
        assert extract_entity_id("[Q123]") == "Q123"

    def test_parentheses(self):
        """Test extracting from parentheses."""
        assert extract_entity_id("(Q123)") == "Q123"

    def test_no_entity_found(self):
        """Test when no entity found."""
        assert extract_entity_id("not an entity") is None
        assert extract_entity_id("") is None

    def test_non_string_input(self):
        """Test non-string input."""
        assert extract_entity_id(None) is None
        assert extract_entity_id(123) is None

    def test_property_id(self):
        """Test extracting property ID."""
        assert extract_entity_id("P31") == "P31"
        assert extract_entity_id("http://www.wikidata.org/prop/direct/P31") == "P31"


class TestGetEntityTypeUri:
    """Tests for get_entity_type_uri function."""

    def test_item_type(self):
        """Test item type URI."""
        uri = get_entity_type_uri("item")
        assert uri == "http://www.wikidata.org/ontology#Item"

    def test_property_type(self):
        """Test property type URI."""
        uri = get_entity_type_uri("property")
        assert uri == "http://www.wikidata.org/ontology#Property"

    def test_lexeme_type(self):
        """Test lexeme type URI."""
        uri = get_entity_type_uri("lexeme")
        assert uri == "http://www.wikidata.org/ontology#Lexeme"

    def test_custom_base_url(self):
        """Test custom base URL."""
        uri = get_entity_type_uri("item", base_url="https://my.wikibase.cloud")
        assert uri == "https://my.wikibase.cloud/ontology#Item"

    def test_case_insensitive(self):
        """Test case insensitive type."""
        uri_upper = get_entity_type_uri("ITEM")
        uri_lower = get_entity_type_uri("item")
        assert uri_upper == uri_lower
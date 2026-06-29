#import sys
import copy
import importlib
import logging
import os
import re
import time
import types
from typing import Any, Optional

import pywikibot

from .claim_builder import ClaimBuilder, build_claim_key
from .config_loader import load_config
from .date_normalizer import DateNormalizer
from .endpoints import get_endpoint, sparql
from .errors import ConfigurationError, DeprecationError, ValidationError
from .validation import validate_pid, validate_qid
from .wikibase_client import WikibaseClient

_logger = logging.getLogger(__name__)

_user_cfg = load_config()

# Legacy module-level mutable state. New code should create a WikibaseClient
# instance; these globals are kept for backward compatibility.
site = None
repo = None
properties = None

# Simple TTL cache for list_properties() result.
_PROPERTIES_CACHE_TTL_SECONDS = 300
_properties_cache = None
_properties_cache_timestamp: float = 0.0

_prefix_block_cache: dict[tuple[str, str], str] = {}

# Default client used by the module-level compatibility facade.
_default_client: Optional[WikibaseClient] = None


def _get_default_client() -> WikibaseClient:
    """Return the lazily-created default WikibaseClient."""
    global _default_client
    if _default_client is None:
        _default_client = WikibaseClient(_user_cfg)
    return _default_client


def _cfg_value(name, default=None):
    # Support both plain and LOD_ prefixed environment variables.
    for env_name in (name, f"LOD_{name}"):
        value = os.getenv(env_name)
        if value is not None:
            return value
    if _user_cfg:
        return getattr(_user_cfg, name, default)
    return default


def _require_cfg(name, value):
    if value:
        return value
    raise ConfigurationError(
        f"Missing {name} (set in lod_config.py or environment variable).",
        name=name,
    )


def _validate_pid(value: Any, field: str = "property") -> None:
    """Raise ValidationError if value is not a valid Property ID."""
    if value and not validate_pid(str(value)):
        raise ValidationError(
            f"Invalid property ID: {value!r}",
            field=field,
            value=value,
        )


def _validate_qid(value: Any, field: str = "item") -> None:
    """Raise ValidationError if value is not a valid Item ID."""
    if value and not validate_qid(str(value)):
        raise ValidationError(
            f"Invalid item ID: {value!r}",
            field=field,
            value=value,
        )


def _wikibase_endpoint_key():
    return _require_cfg(
        "WIKIBASE_ENDPOINT_KEY",
        _cfg_value("WIKIBASE_ENDPOINT_KEY"),
    )


def _wikibase_project_code():
    """Project code used as namespace prefix base (e.g. 'fg', 'mywiki')."""
    return _require_cfg(
        "WIKIBASE_PROJECT_CODE",
        _cfg_value("WIKIBASE_PROJECT_CODE"),
    )


def _wikibase_host():
    """Host used to build Wikibase RDF namespace IRIs (without protocol)."""
    host = _require_cfg(
        "WIKIBASE_HOST",
        _cfg_value("WIKIBASE_HOST"),
    )
    host = re.sub(r"^https?://", "", host.strip())
    return host.rstrip("/")


def _prefix(derived_suffix):
    return f"{_wikibase_project_code()}_{derived_suffix}"


def _prefix_wdt():
    return _prefix("wdt")


def _prefix_wd():
    return _prefix("wd")


def _prefix_pq():
    return _prefix("pq")


def _prefix_ps():
    return _prefix("ps")


def _wikibase_prefix_block():
    """
    Build PREFIX declarations for generated {PROJECT_CODE}_* aliases.

    Prefix declarations are required and derived from project code and host.
    The result is cached per (project_code, host) so repeated calls do not
    rebuild the string.
    """
    global _prefix_block_cache
    project_code = _wikibase_project_code()
    host = _wikibase_host()
    cache_key = (project_code, host)

    prefix_block = _prefix_block_cache.get(cache_key)
    if prefix_block is not None:
        return prefix_block

    prefix_block = (
        f"PREFIX {_prefix_wd()}: <http://{host}/entity/>\n"
        f"PREFIX {_prefix_wdt()}: <http://{host}/prop/direct/>\n"
        f"PREFIX {_prefix_pq()}: <http://{host}/prop/qualifier/>\n"
        f"PREFIX {_prefix_ps()}: <http://{host}/prop/statement/>\n"
    )
    _prefix_block_cache[cache_key] = prefix_block
    return prefix_block


def _with_wikibase_prefixes(query):
    return _wikibase_prefix_block() + query


def _equivalent_p31():
    """Local equivalent of Wikidata P31 (instance of / type)."""
    return _cfg_value("WIKIBASE_EQUIVALENT_P31", "P31")


def _equivalent_p1932():
    """Local equivalent of Wikidata P1932 (object stated as — original string qualifier)."""
    return _cfg_value("WIKIBASE_EQUIVALENT_P1932", "P1932")


def _equivalent_q486972():
    """Local equivalent of Wikidata Q486972 (human settlement — used as type filter)."""
    return _cfg_value("WIKIBASE_EQUIVALENT_Q486972", "Q486972")


def _escape_sparql_literal(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _ensure_site_repo():
    global site, repo
    if repo is not None:
        return repo

    client = _get_default_client()
    site = client.site()
    repo = client.repo()
    return repo


def _ensure_properties():
    global properties, _properties_cache, _properties_cache_timestamp
    if properties is not None:
        return properties
    if _properties_cache is not None:
        age = time.monotonic() - _properties_cache_timestamp
        if age < _PROPERTIES_CACHE_TTL_SECONDS:
            return _properties_cache
    properties = _get_default_client().properties()
    _properties_cache = properties
    _properties_cache_timestamp = time.monotonic()
    return properties


def refresh_properties():
    """Invalidate the cached properties map and force a reload.

    Useful after creating new properties on the Wikibase instance.
    """
    global properties, _properties_cache, _properties_cache_timestamp
    properties = None
    _properties_cache = None
    _properties_cache_timestamp = 0.0
    _get_default_client().refresh_properties()


############### Normalisation helpers ###############


def multi_replace(rules, data: str) -> str:
    ret = data
    for pattern, repl in rules:
        ret = re.sub(pattern, repl, ret)
    return ret


datum_regex = [
    (r"(\[ *| *\])", ""),
    (r"^ +", ""),
    ("VIII", "08"),
    ("III", "03"),
    ("VII", "07"),
    ("XII", "12"),
    ("II", "02"),
    ("VI", "06"),
    ("XI", "11"),
    ("IV", "04"),
    ("IX", "09"),
    ("V", "05"),
    ("X", "10"),
    ("I", "01"),
    (r"^([0-9]{4})([0-9]{2})([0-9]{2})$", r"\1-\2-\3"),
    (r"^([0-9]{1,2})\. *([0-9]{1,2})\. *([0-9]{4})$", r"\3-\2-\1"),
    (r"^([0-9]{1,2})\. *([0-9]{4})$", r"\2-\1"),
    (r"^([0-9])-", r"0\1-"),
    (r"-([0-9])-", r"-0\1-"),
    (r"-([0-9])$", r"-0\1"),
    (r"^([0-9]{4})-00-00$", r"\1"),
    (r"^([0-9]{4}-[0-9]{2})-00$", r"\1"),
]


# Lazily-created default normalizer used by the legacy normal_dat helper.
_default_date_normalizer: DateNormalizer = DateNormalizer(roman_numerals=True)


def normal_dat(datum: str) -> str:
    """Normalize a date string into ISO-like Wikibase Time format.

    Keeps the legacy Roman-numeral behavior for backward compatibility.
    New code can use ``DateNormalizer`` directly for safer defaults.
    """
    return _default_date_normalizer.normalize(datum)


############### Wikibase SPARQL helpers ###############


def list_properties(db=None):
    query = "SELECT * WHERE { ?property a wikibase:Property; wikibase:propertyType ?datatype. }"
    result = sparql(get_endpoint(_wikibase_endpoint_key()), query)
    props = {}
    for p in result["results"]["bindings"]:
        prop_id = p["property"]["value"].split("/")[-1]
        prop_datatype = p["datatype"]["value"].split("#")[-1]
        props[prop_id] = prop_datatype
    return props

def check_by_label_desc(label, desc, lang="cs"):
    safe_label = _escape_sparql_literal(label)
    safe_desc = _escape_sparql_literal(desc)
    query = _with_wikibase_prefixes(
        f'SELECT ?item WHERE {{ ?item rdfs:label "{safe_label}"@{lang}; schema:description "{safe_desc}"@{lang}. }}'
    )
    result = sparql(get_endpoint(_wikibase_endpoint_key()), query)
    items = result["results"]["bindings"]
    if len(items) == 0:
        return "create"
    if len(items) == 1:
        repo_obj = _ensure_site_repo()
        return pywikibot.ItemPage(repo_obj, items[0]["item"]["value"].split("/")[-1])
    _logger.warning("SPARQL has found more than one item with label %s and description %s: %s", label, desc, [item["item"]["value"] for item in items])
    return None

def checkID(property, ID):
    _validate_pid(property)
    repo_obj = _ensure_site_repo()
    safe_id = _escape_sparql_literal(ID)
    query = _with_wikibase_prefixes(
        f'SELECT ?item WHERE {{ ?item {_prefix_wdt()}:{property} "{safe_id}" }}'
    )
    check_id = sparql(get_endpoint(_wikibase_endpoint_key()), query)
    result = check_id["results"]["bindings"]
    if len(result) == 0:
        return "create"
    if len(result) == 1:
        return pywikibot.ItemPage(repo_obj, result[0]["item"]["value"].split("/")[-1])
    _logger.warning("checkID found %s matches for %s=%s", len(result), property, ID)
    return None


############ String-to-QID converters ###########


def label2entity(type, string, lang="cs", limit=10):
    if type:
        _validate_qid(type, field="type")
    if string != "":
        safe_string = _escape_sparql_literal(string)
        if type:
            queryType = f"?item {_prefix_wdt()}:{_equivalent_p31()} {_prefix_wd()}:{type}."
        else:
            queryType = ""
        query = _with_wikibase_prefixes(
            "SELECT DISTINCT ?item WHERE { "
            f"{queryType} "
            f"?item (rdfs:label|skos:altLabel) \"{safe_string}\"@{lang}. }}"
            f" LIMIT {limit}"
        )
        result = sparql(get_endpoint(_wikibase_endpoint_key()), query)["results"]["bindings"]
        if len(result) == 1:
            return result[0]["item"]["value"].split("/")[-1]
        return None


def string2entity(property, string, limit=10):
    _validate_pid(property)
    if string != "":
        safe_string = _escape_sparql_literal(string)
        query = _with_wikibase_prefixes(
            "SELECT DISTINCT ?item WHERE { "
            f"?statement {_prefix_pq()}:{_equivalent_p1932()} \"{safe_string}\"; "
            f"{_prefix_ps()}:{property} ?item. }}"
            f" LIMIT {limit}"
        )
        result = sparql(get_endpoint(_wikibase_endpoint_key()), query)["results"]["bindings"]
        if len(result) == 1:
            return result[0]["item"]["value"].split("/")[-1]
        return None

def add_claim_loc(item, data, locString, propItem, propString):
    _validate_pid(propItem, field="propItem")
    _validate_pid(propString, field="propString")
    locQ = string2entity(propItem, locString)
    if not locQ:
        locQ = label2entity(_equivalent_q486972(), locString)

    if locQ:
        data = add_claim(item, data, propItem, locQ, quals=[[_equivalent_p1932(), locString]])
    else:
        data = add_claim(item, data, propString, locString)

    return data


############### Wikibase editing helpers ###############


def create_item(data, summ):
    repo_obj = _ensure_site_repo()
    new_item = pywikibot.ItemPage(repo_obj)
    try:
        new_item.editEntity(data, summary=summ)
        labels = data.get("labels", {})
        label_value = labels.get("cs") or labels.get("de") or next(iter(labels.values()), "<no label>")
        _logger.info("Item %s does not exist, created: %s", label_value, new_item)
    except pywikibot.exceptions.OtherPageSaveError as error:
        match = re.search(r"\[\[Item:Q(\d+)\|Q\1\]\]", str(error))
        if match:
            item_exist = match.group(1)
            new_item = pywikibot.ItemPage(repo_obj, f"Q{item_exist}")
        else:
            _logger.error("Failed to create item: %s", error)
            raise
    return new_item


def get_statement_id(item, property, value, quals=None, restrictive=False, rank=None):
    _validate_pid(property)
    if item != "create" and hasattr(item, "claims"):
        if property in item.claims:
            for statement in item.claims[property]:
                # Normalize value and decide whether a Quantity unit must match.
                str_value = str(value).lstrip("+")
                include_unit = "Q" in str_value
                match_found = _get_claim_value(statement, include_unit=include_unit) == str_value

                if match_found:
                    if rank and statement.rank != rank:
                        continue

                    if quals:
                        all_qualifiers_match = True

                        for qualifier_property, qualifier_value in quals:
                            if qualifier_property not in statement.qualifiers:
                                all_qualifiers_match = False
                                break

                            qualifier_match_found = False
                            str_qualifier_value = str(qualifier_value).lstrip("+")
                            include_qual_unit = "Q" in str_qualifier_value
                            for qualifier in statement.qualifiers[qualifier_property]:
                                if _get_claim_value(qualifier, include_unit=include_qual_unit) == str_qualifier_value:
                                    qualifier_match_found = True
                                    break

                            if not qualifier_match_found:
                                all_qualifiers_match = False
                                break

                        if restrictive and all_qualifiers_match:
                            if len(statement.qualifiers) != len(quals):
                                all_qualifiers_match = False

                        if all_qualifiers_match:
                            return statement.snak
                    else:
                        return statement.snak

    return None


def add_claim(item, data, property, value, quals=None, restrictive=True, rank="normal", unit=None, references=None):
    """
    Add a claim to an entity.
    
    Args:
        item: The item to add the claim to
        data: The data dict containing claims
        property: Property ID (e.g., 'P1')
        value: The value to set
        quals: List of qualifier tuples [(property, value), ...]
        restrictive: Whether to match all qualifiers exactly
        rank: Claim rank ('normal', 'preferred', 'deprecated')
        unit: Unit Q-ID for Quantity type (e.g., 'Q11573' for meter)
        references: Optional reference snaks, e.g. [("P48", "Q123"), ("P854", "https://example.org")]
    """
    _validate_pid(property)
    if value != "":
        properties_map = _ensure_properties()
        value = value.strip()
        prop_type = properties_map.get(property)

        if prop_type == "Time":
            value = normal_dat(value)

        # Build comparison key including unit for Quantity values.
        _, compare_value = build_claim_key(
            property, value, properties_map=properties_map, unit=unit
        )

        exist = get_statement_id(
            item, property, compare_value, quals=quals, restrictive=restrictive, rank=rank
        )
        if exist is None:
            builder = ClaimBuilder(properties_map, _wikibase_host())
            claim_data = builder.build_claim(
                property, value, rank=rank, unit=unit, references=references
            )
            if claim_data is None:
                return data

            if quals:
                claim_data["qualifiers"] = []
                for qual in quals:
                    qual_data = builder.build_qualifier(qual[0], qual[1])
                    if qual_data is not None:
                        claim_data["qualifiers"].append(qual_data)
            data["claims"].append(claim_data)
    return data


def _deprecated_legacy_helper(name: str, replacement: str) -> None:
    """Raise DeprecationError pointing to the recommended replacement."""
    raise DeprecationError(
        f"{name}() was removed. Use {replacement} instead.",
        replacement=replacement,
    )


def add_qualifier(claim, ec, p, value, summ):
    """
    Deprecated legacy helper.

    Direct pywikibot qualifier editing is no longer supported. Build the
    qualifier via ``add_claim(..., quals=[(p, value)])`` and commit the change
    with ``item.editEntity(data, summary=...)``.
    """
    _deprecated_legacy_helper(
        "add_qualifier",
        "add_claim(item, data, property, value, quals=[(p, value)]) + item.editEntity(data, summary=...)",
    )


def add_qualifier_data(properties_map, qual):
    """
    Build qualifier data dict for batch API (used by add_claim with quals parameter).

    Args:
        properties_map: Dict mapping property IDs to their types
        qual: Tuple of (property_id, value)

    Returns:
        Dict with qualifier snak structure or None if invalid
    """
    builder = ClaimBuilder(properties_map, _wikibase_host())
    return builder.build_qualifier(qual[0], qual[1])


def add_qualifier_q(claim, ec, p, q, summ):
    _deprecated_legacy_helper(
        "add_qualifier_q",
        "add_claim(item, data, property, value, quals=[(p, value)]) + item.editEntity(data, summary=...)",
    )


def add_qualifier_str(claim, ec, p, string, summ):
    _deprecated_legacy_helper(
        "add_qualifier_str",
        "add_claim(item, data, property, value, quals=[(p, value)]) + item.editEntity(data, summary=...)",
    )


def add_qualifier_dat(claim, ec, p, string, summ):
    _deprecated_legacy_helper(
        "add_qualifier_dat",
        "add_claim(item, data, property, value, quals=[(p, value)]) + item.editEntity(data, summary=...)",
    )


def remove_claim(item, data, property, value, quals=None, restrictive=False, rank=None):
    _validate_pid(property)
    exist = get_statement_id(item, property, value, quals=quals, restrictive=restrictive, rank=rank)
    if exist:
        remove_data = {
            "id": exist,
            "remove": "",
        }
        data["claims"].append(remove_data)
    return data


def remove_claim_id(item, data, id):
    remove_data = {
        "id": id,
        "remove": "",
    }
    data["claims"].append(remove_data)
    return data


def remove_property(item, data, property):
    """
    Remove all statements of the given property from the entity.

    Args:
        item: The entity to modify
        data: The data dict containing claims
        property: Property ID (e.g., 'P1')

    Returns:
        The updated data dict.
    """
    _validate_pid(property)
    if item != "create" and hasattr(item, "claims"):
        if property in item.claims:
            for statement in item.claims[property]:
                data["claims"].append({
                    "id": statement.snak,
                    "remove": "",
                })
    return data


def _get_claim_value(statement, include_unit=True):
    """Extract a comparable value from a pywikibot Claim statement target."""
    target = statement.getTarget()

    if isinstance(target, str):
        return target
    if isinstance(target, pywikibot.page.ItemPage):
        return target.getID()
    if isinstance(target, pywikibot.WbMonolingualText):
        return target.text
    if isinstance(target, pywikibot.WbTime):
        if target.precision == 11:
            return f"{target.year}-{target.month:02d}-{target.day:02d}"
        if target.precision == 10:
            return f"{target.year}-{target.month:02d}"
        if target.precision == 9:
            return f"{target.year}"
    if isinstance(target, pywikibot.WbQuantity):
        amount = str(target.amount).lstrip("+")
        if include_unit and target.unit:
            unit_id = target.unit.getID() if hasattr(target.unit, "getID") else target.unit.split("/")[-1]
            unit_id = unit_id.replace("Q", "")
            return f"{amount}Q{unit_id}"
        return amount

    return None


def update_unique_property(item, data, property, value, quals=None, rank="normal", unit=None):
    """
    Update a property that must have at most one value.

    If the property already has exactly one statement with the same value,
    no edit is performed. Otherwise, all existing statements of the property
    are removed and the new claim is added.

    Args:
        item: The entity to modify
        data: The data dict containing claims
        property: Property ID (e.g., 'P1')
        value: The new value to set
        quals: List of qualifier tuples [(property, value), ...]
        rank: Claim rank ('normal', 'preferred', 'deprecated')
        unit: Unit Q-ID for Quantity type

    Returns:
        The updated data dict.
    """
    _validate_pid(property)
    if value == "":
        return data

    existing_statements = []
    if item != "create" and hasattr(item, "claims"):
        existing_statements = item.claims.get(property, [])

    # Build comparison key including unit for Quantity values.
    properties_map = None
    if unit:
        properties_map = _ensure_properties()
    _, compare_value = build_claim_key(
        property, value, properties_map=properties_map or {}, unit=unit
    )

    # Find the first statement whose value already matches the desired value.
    matching_statement = None
    for statement in existing_statements:
        if _get_claim_value(statement) == compare_value:
            matching_statement = statement
            break

    if matching_statement is not None:
        # Keep one matching statement and remove all other statements of this
        # property, including duplicate statements with the same value.
        for statement in existing_statements:
            if statement is not matching_statement:
                data["claims"].append({
                    "id": statement.snak,
                    "remove": "",
                })
        return data

    # No matching statement exists: remove all existing statements and add
    # the new one. Because remove_property only records removals in data,
    # item.claims still contains the old statements, which would prevent
    # add_claim from adding the new claim. Use a temporary item with the
    # property cleared for the existence check.
    if existing_statements:
        data = remove_property(item, data, property)

    # Use a temporary item with the property cleared so add_claim does not
    # see the old statements that are already scheduled for removal.
    # If the property is already absent/empty, the original item is fine.
    if (
        item != "create"
        and hasattr(item, "claims")
        and property in item.claims
        and item.claims[property]
    ):
        temp_claims = copy.deepcopy(item.claims)
        temp_claims[property] = []
        temp_item = types.SimpleNamespace(claims=temp_claims)
    else:
        temp_item = item

    data = add_claim(temp_item, data, property, value, quals=quals, rank=rank, unit=unit)

    return data


def remove_claim_q(item, ec, p, q, summ):
    _deprecated_legacy_helper(
        "remove_claim_q",
        "remove_claim(item, data, property, value) + item.editEntity(data, summary=...)",
    )


def remove_claim_str(item, ec, p, string, summ):
    _deprecated_legacy_helper(
        "remove_claim_str",
        "remove_claim(item, data, property, value) + item.editEntity(data, summary=...)",
    )


def remove_claim_dat(item, ec, p, string, summ):
    _deprecated_legacy_helper(
        "remove_claim_dat",
        "remove_claim(item, data, property, value) + item.editEntity(data, summary=...)",
    )


def remove_qualifier_str(claim, ec, p, string, summ):
    _deprecated_legacy_helper(
        "remove_qualifier_str",
        "remove_claim(item, data, property, value) + item.editEntity(data, summary=...)",
    )


def add_ref(claim, link, summ):
    repo_obj = _ensure_site_repo()
    try:
        claim.getSources()
    except pywikibot.exceptions.Error as error:
        _logger.debug("Cannot fetch existing sources: %s", error)

    claimJSON = claim.toJSON()
    new_ref = pywikibot.Claim(repo_obj, "P48")
    new_ref.setTarget(link)

    addRef = True
    if "references" in claimJSON:
        refs = [
            ref["snaks"]["P48"][0]["datavalue"]["value"]["numeric-id"]
            for ref in claimJSON["references"]
            if "P48" in ref["snaks"]
        ]
        numID = int(re.sub(r".*Q([0-9]+)\]\]", r"\1", str(link)))
        if numID in refs:
            addRef = False
    if addRef:
        claim.addSource(new_ref, summary="+reference")
        _logger.info("Reference added")


def __getattr__(name):
    if name == "repo":
        return _ensure_site_repo()
    if name == "properties":
        return _ensure_properties()
    if name == "WIKIBASE_PROJECT_CODE":
        return _wikibase_project_code()
    if name == "WIKIBASE_HOST":
        return _wikibase_host()
    if name == "WIKIBASE_EQUIVALENT_P31":
        return _equivalent_p31()
    if name == "WIKIBASE_EQUIVALENT_P1932":
        return _equivalent_p1932()
    if name == "WIKIBASE_EQUIVALENT_Q486972":
        return _equivalent_q486972()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


#import sys
import importlib
import logging
import os
import re
#import time

import pywikibot

from .endpoints import get_endpoint, sparql
from .config_loader import load_config

_logger = logging.getLogger(__name__)

_user_cfg = load_config()

site = None
repo = None
properties = None


def _cfg_value(env_name, cfg_name, default=None):
    value = os.getenv(env_name)
    if value is not None:
        return value
    if _user_cfg:
        return getattr(_user_cfg, cfg_name, default)
    return default


def _require_cfg(name, value):
    if value:
        return value
    raise RuntimeError(
        f"Missing {name} (set in lod_config.py or environment variable)."
    )


def _wikibase_endpoint_key():
    return _require_cfg(
        "WIKIBASE_ENDPOINT_KEY / LOD_WIKIBASE_ENDPOINT_KEY",
        _cfg_value("LOD_WIKIBASE_ENDPOINT_KEY", "WIKIBASE_ENDPOINT_KEY"),
    )


def _wikibase_project_code():
    """Project code used as namespace prefix base (e.g. 'fg', 'mywiki')."""
    return _require_cfg(
        "WIKIBASE_PROJECT_CODE / LOD_WIKIBASE_PROJECT_CODE",
        _cfg_value("LOD_WIKIBASE_PROJECT_CODE", "WIKIBASE_PROJECT_CODE"),
    )


def _wikibase_host():
    """Host used to build Wikibase RDF namespace IRIs (without protocol)."""
    host = _require_cfg(
        "WIKIBASE_HOST / LOD_WIKIBASE_HOST",
        _cfg_value("LOD_WIKIBASE_HOST", "WIKIBASE_HOST"),
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
    """
    project_code = _wikibase_project_code()
    host = _wikibase_host()

    return (
        f"PREFIX {_prefix_wd()}: <http://{host}/entity/>\n"
        f"PREFIX {_prefix_wdt()}: <http://{host}/prop/direct/>\n"
        f"PREFIX {_prefix_pq()}: <http://{host}/prop/qualifier/>\n"
        f"PREFIX {_prefix_ps()}: <http://{host}/prop/statement/>\n"
    )


def _with_wikibase_prefixes(query):
    return _wikibase_prefix_block() + query


def _equivalent_p31():
    """Local equivalent of Wikidata P31 (instance of / type)."""
    return _cfg_value("LOD_WIKIBASE_EQUIVALENT_P31", "WIKIBASE_EQUIVALENT_P31", "P31")


def _equivalent_p1932():
    """Local equivalent of Wikidata P1932 (object stated as — original string qualifier)."""
    return _cfg_value("LOD_WIKIBASE_EQUIVALENT_P1932", "WIKIBASE_EQUIVALENT_P1932", "P1932")


def _equivalent_q486972():
    """Local equivalent of Wikidata Q486972 (human settlement — used as type filter)."""
    return _cfg_value("LOD_WIKIBASE_EQUIVALENT_Q486972", "WIKIBASE_EQUIVALENT_Q486972", "Q486972")


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

    wikibase_site_code = _require_cfg(
        "WIKIBASE_SITE_CODE / LOD_WIKIBASE_SITE_CODE",
        _cfg_value("LOD_WIKIBASE_SITE_CODE", "WIKIBASE_SITE_CODE"),
    )
    wikibase_site_family = _require_cfg(
        "WIKIBASE_SITE_FAMILY / LOD_WIKIBASE_SITE_FAMILY",
        _cfg_value("LOD_WIKIBASE_SITE_FAMILY", "WIKIBASE_SITE_FAMILY"),
    )

    site = pywikibot.Site(wikibase_site_code, wikibase_site_family)
    repo = site.data_repository()
    return repo


def _ensure_properties():
    global properties
    if properties is None:
        properties = list_properties()
    return properties


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


def normal_dat(datum):
    normalDat = multi_replace(datum_regex, datum)
    return normalDat


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


def checkID(property, ID):
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


def label2entity(type, string):
    if string != "":
        safe_string = _escape_sparql_literal(string)
        if type:
            queryType = f"?item {_prefix_wdt()}:{_equivalent_p31()} {_prefix_wd()}:{type}."
        else:
            queryType = ""
        query = _with_wikibase_prefixes(
            "SELECT DISTINCT ?item WHERE { "
            f"{queryType} "
            f"?item (rdfs:label|skos:altLabel) \"{safe_string}\"@cs. }}"
        )
        result = sparql(get_endpoint(_wikibase_endpoint_key()), query)["results"]["bindings"]
        if len(result) == 1:
            return result[0]["item"]["value"].split("/")[-1]
        return None


def string2entity(property, string):
    if string != "":
        safe_string = _escape_sparql_literal(string)
        query = _with_wikibase_prefixes(
            "SELECT DISTINCT ?item WHERE { "
            f"?statement {_prefix_pq()}:{_equivalent_p1932()} \"{safe_string}\"; "
            f"{_prefix_ps()}:{property} ?item. }}"
        )
        result = sparql(get_endpoint(_wikibase_endpoint_key()), query)["results"]["bindings"]
        if len(result) == 1:
            return result[0]["item"]["value"].split("/")[-1]
        return None

def add_claim_loc(item, data, locString, propItem, propString):
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
        item_exist = re.search(r"\[\[Item:Q(\d+)\|Q\1\]\]", str(error)).group(1)
        new_item = pywikibot.ItemPage(repo_obj, f"Q{item_exist}")
    return new_item


def get_statement_id(item, property, value, quals=None, restrictive=False, rank=None):
    if item != "create":
        if property in item.claims:
            for statement in item.claims[property]:
                target = statement.getTarget()

                if isinstance(target, str) and target == value:
                    match_found = True
                elif isinstance(target, pywikibot.page.ItemPage) and target.getID() == value:
                    match_found = True
                elif isinstance(target, pywikibot.WbTime):
                    if target.precision == 11:
                        statement_value = f"{target.year}-{target.month:02d}-{target.day:02d}"
                    elif target.precision == 10:
                        statement_value = f"{target.year}-{target.month:02d}"
                    elif target.precision == 9:
                        statement_value = f"{target.year}"
                    match_found = statement_value == value
                else:
                    match_found = False

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
                            for qualifier in statement.qualifiers[qualifier_property]:
                                qualifier_target = qualifier.getTarget()

                                if isinstance(qualifier_target, str) and qualifier_target == qualifier_value:
                                    qualifier_match_found = True
                                    break
                                if isinstance(qualifier_target, pywikibot.page.ItemPage) and qualifier_target.getID() == qualifier_value:
                                    qualifier_match_found = True
                                    break
                                if isinstance(qualifier_target, pywikibot.WbTime):
                                    if qualifier_target.precision == 11:
                                        qualifier_value_str = f"{qualifier_target.year}-{qualifier_target.month:02d}-{qualifier_target.day:02d}"
                                    elif qualifier_target.precision == 10:
                                        qualifier_value_str = f"{qualifier_target.year}-{qualifier_target.month:02d}"
                                    elif qualifier_target.precision == 9:
                                        qualifier_value_str = f"{qualifier_target.year}"

                                    if qualifier_value_str == qualifier_value:
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


def add_claim(item, data, property, value, quals=None, restrictive=True, rank="normal"):
    if value != "":
        properties_map = _ensure_properties()
        value = value.strip()
        if properties_map[property] == "Time":
            value = normal_dat(value)
        exist = get_statement_id(item, property, value, quals=quals, restrictive=restrictive, rank=rank)
        if exist is None:
            claim_data = {
                "mainsnak": {
                    "snaktype": "value",
                    "property": property,
                    "datavalue": {},
                },
                "type": "statement",
                "rank": rank,
            }
            if properties_map[property] == "WikibaseItem":
                claim_data["mainsnak"]["datavalue"] = {
                    "value": {
                        "entity-type": "item",
                        "numeric-id": value.replace("Q", ""),
                    },
                    "type": "wikibase-entityid",
                }
            elif properties_map[property] in ["String", "ExternalId", "Url", "url"]:
                claim_data["mainsnak"]["datavalue"] = {
                    "type": "string",
                    "value": value,
                }
            elif properties_map[property] == "Time":
                if re.match(r"\d{4}-\d{2}-\d{2}", value):
                    time = value
                    precision = 11
                elif re.match(r"\d{4}-\d{2}", value):
                    time = value + "-00"
                    precision = 10
                elif re.match(r"\d{4}", value):
                    time = value + "-00-00"
                    precision = 9
                else:
                    return data

                claim_data["mainsnak"]["datavalue"] = {
                    "value": {
                        "time": "+" + time + "T00:00:00Z",
                        "precision": precision,
                        "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
                        "timezone": 0,
                        "after": 0,
                        "before": 0,
                    },
                    "type": "time",
                }
            if quals:
                claim_data["qualifiers"] = []
                for qual in quals:
                    qual_data = add_qualifier(properties_map, qual)
                    if qual_data is not None:
                        claim_data["qualifiers"].append(qual_data)
            data["claims"].append(claim_data)
    return data


def add_claim_amount(item, ec, p, value, unit, summ):
    repo_obj = _ensure_site_repo()
    valNormal = value.strip()
    qexist = []
    if p in ec["claims"]:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            amount = val["mainsnak"]["datavalue"]["value"]["amount"]
            unit = val["mainsnak"]["datavalue"]["value"]["unit"].split("/")[-1]
            valJoin = amount + unit
            qexist.append(valJoin)
    valNewJoin = "+" + str(valNormal) + str(unit)
    if valNewJoin in qexist:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            if val["mainsnak"]["datavalue"]["value"] == valNormal:
                return cl
    else:
        _logger.info("Creating claim %s=%s", p, valNormal)
        claim = pywikibot.Claim(repo_obj, p)
        unitForm = pywikibot.ItemPage(repo_obj, unit)
        target = pywikibot.WbQuantity(site=repo_obj, amount=valNormal, unit=unitForm)
        claim.setTarget(target)
        item.addClaim(claim, summary=summ)
        return claim


def add_claim_monoling(item, ec, p, string, summ):
    repo_obj = _ensure_site_repo()
    qexist = []
    if p in ec["claims"]:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            qexist.append(val["mainsnak"]["datavalue"]["value"]["text"])
    if string in qexist:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            if val["mainsnak"]["datavalue"]["value"]["text"] == string:
                return cl
    else:
        _logger.info("Creating claim %s=%s", p, string)
        claim = pywikibot.Claim(repo_obj, p)
        target = pywikibot.WbMonolingualText(string, "cs")
        claim.setTarget(target)
        item.addClaim(claim, summary=summ)
        return claim


def add_qualifier(properties_map, qual):
    qual_data = {
        "snaktype": "value",
        "property": qual[0],
    }
    if properties_map[qual[0]] == "WikibaseItem":
        qual_data["datavalue"] = {
            "value": {
                "entity-type": "item",
                "numeric-id": qual[1].replace("Q", ""),
            },
            "type": "wikibase-entityid",
        }
    elif properties_map[qual[0]] in ["String", "ExternalId", "Url", "url"]:
        qual_data["datavalue"] = {
            "value": qual[1],
            "type": "string",
        }
    elif properties_map[qual[0]] == "Time":
        if re.match(r"\d{4}-\d{2}-\d{2}", qual[1]):
            time = qual[1]
            precision = 11
        elif re.match(r"\d{4}-\d{2}", qual[1]):
            time = qual[1] + "-00"
            precision = 10
        elif re.match(r"\d{4}", qual[1]):
            time = qual[1] + "-00-00"
            precision = 9
        else:
            return None

        qual_data["datavalue"] = {
            "value": {
                "time": "+" + time + "T00:00:00Z",
                "precision": precision,
                "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
                "timezone": 0,
                "after": 0,
                "before": 0,
            },
            "type": "time",
        }

    return qual_data


def add_qualifier_q(claim, ec, p, q, summ):
    repo_obj = _ensure_site_repo()
    qexist = []
    val = claim.toJSON()
    if "qualifiers" in val and p in val["qualifiers"]:
        for qual in val["qualifiers"][p]:
            qexist.append("Q" + str(qual["datavalue"]["value"]["numeric-id"]))
    if q not in qexist:
        qualifier = pywikibot.Claim(repo_obj, p)
        target = pywikibot.ItemPage(repo_obj, q)
        qualifier.setTarget(target)
        claim.addQualifier(qualifier, summary="+qualifier")


def add_qualifier_str(claim, ec, p, string, summ):
    repo_obj = _ensure_site_repo()
    strNormal = string.strip()
    qexist = []
    val = claim.toJSON()
    if "qualifiers" in val and p in val["qualifiers"]:
        for qual in val["qualifiers"][p]:
            qexist.append(qual["datavalue"]["value"])
    if strNormal not in qexist:
        qualifier = pywikibot.Claim(repo_obj, p)
        qualifier.setTarget(strNormal)
        claim.addQualifier(qualifier, summary="+qualifier")


def add_qualifier_dat(claim, ec, p, string, summ):
    repo_obj = _ensure_site_repo()
    qexist = []
    val = claim.toJSON()
    if "qualifiers" in val and p in val["qualifiers"]:
        for qual in val["qualifiers"][p]:
            precision = qual["datavalue"]["value"]["precision"]
            if precision == 11:
                date = re.sub(r".*(\d{4}-\d{2}-\d{2}).*", r"\1", qual["datavalue"]["value"]["time"])
            elif precision == 10:
                date = re.sub(r".*(\d{4}-\d{2}).*", r"\1", qual["datavalue"]["value"]["time"])
            elif precision == 9:
                date = re.sub(r".*(\d{4}).*", r"\1", qual["datavalue"]["value"]["time"])
            qexist.append(date)
    if string not in qexist:
        qualifier = pywikibot.Claim(repo_obj, p)
        if re.match(r"\d{4}-\d{2}-\d{2}", string):
            timestamp = pywikibot.Timestamp.fromISOformat(string + "T00:00:00Z")
            target = pywikibot.WbTime.fromTimestamp(timestamp, precision=11)
        elif re.match(r"\d{4}-\d{2}", string):
            timestamp = pywikibot.Timestamp.fromISOformat(string + "-01T00:00:00Z")
            target = pywikibot.WbTime.fromTimestamp(timestamp, precision=10)
        elif re.match(r"\d{4}", string):
            timestamp = pywikibot.Timestamp.fromISOformat(string + "-01-01T00:00:00Z")
            target = pywikibot.WbTime.fromTimestamp(timestamp, precision=9)
        qualifier.setTarget(target)
        claim.addQualifier(qualifier, summary="+qualifier")


def remove_claim(item, data, property, value, quals=None, restrictive=False, rank=None):
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


def remove_claim_q(item, ec, p, q, summ):
    qexist = []
    if p in ec["claims"]:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            qexist.append("Q" + str(val["mainsnak"]["datavalue"]["value"]["numeric-id"]))
    if q in qexist:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            if val["mainsnak"]["datavalue"]["value"]["numeric-id"] == int(re.sub("Q", "", q)):
                _logger.info("Removing claim %s=%s", p, q)
                item.removeClaims(cl, summary=summ)


def remove_claim_str(item, ec, p, string, summ):
    strNormal = string.strip()
    qexist = []
    if p in ec["claims"]:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            qexist.append(val["mainsnak"]["datavalue"]["value"])
    if strNormal in qexist:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            if val["mainsnak"]["datavalue"]["value"] == strNormal:
                _logger.info("Removing claim %s=%s", p, strNormal)
                item.removeClaims(cl, summary=summ)


def remove_claim_dat(item, ec, p, string, summ):
    strNormal = string.strip()
    qexist = []
    if p in ec["claims"]:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            date = re.sub(r".*(\d{4}-\d{2}-\d{2}).*", r"\1", val["mainsnak"]["datavalue"]["value"]["time"])
            qexist.append(date)
    if strNormal in qexist:
        for cl in ec["claims"][p]:
            val = cl.toJSON()
            if re.sub(r".*(\d{4}-\d{2}-\d{2}).*", r"\1", val["mainsnak"]["datavalue"]["value"]["time"]) == strNormal:
                _logger.info("Removing claim %s=%s", p, strNormal)
                item.removeClaims(cl, summary=summ)


def remove_qualifier_str(claim, ec, p, string, summ):
    strNormal = string.strip()
    if p in claim.qualifiers:
        for qual in claim.qualifiers[p]:
            if qual.getTarget() == strNormal:
                claim.removeQualifier(qual, summary=summ)


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


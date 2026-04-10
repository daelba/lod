#import sys
import re
#import time

import pywikibot

from .endpoints import *

scrap = pywikibot.Site("gotha", "gotha")
repo = scrap.data_repository()

############### Funkce pro normalizaci ###############

def multi_replace(rules, data: str) -> str:
	ret = data
	for pattern, repl in rules:
		ret = re.sub(pattern, repl, ret)
	return ret

datum_regex = [
	(r'(\[ *| *\])',''),
	(r'^ +',''),
	('VIII','08'),
	('III','03'),
	('VII','07'),
	('XII','12'),
	('II','02'),
	('VI','06'),
	('XI','11'),
	('IV','04'),
	('IX','09'),
	('V','05'),
	('X','10'),
	('I','01'),
	(r'^([0-9]{4})([0-9]{2})([0-9]{2})$',r'\1-\2-\3'),
	(r'^([0-9]{1,2})\. *([0-9]{1,2})\. *([0-9]{4})$',r'\3-\2-\1'),
	(r'^([0-9]{1,2})\. *([0-9]{4})$',r'\2-\1'),
	(r'^([0-9])-',r'0\1-'),
	(r'-([0-9])-',r'-0\1-'),
	(r'-([0-9])$',r'-0\1'),
	(r'^([0-9]{4})-00-00$',r'\1'),
	(r'^([0-9]{4}-[0-9]{2})-00$',r'\1')
	]

def normal_dat (datum):
	normalDat = multi_replace (datum_regex, datum)
	return normalDat

############### Funkce pro SPARQL Wikibase ###############

def list_properties (db=None):
	query = 'SELECT * WHERE { ?property a wikibase:Property; wikibase:propertyType ?datatype. }'
	result = sparql(endpoint_gotha, query)
	properties = {}
	for p in result["results"]["bindings"]:
		prop_id = p["property"]["value"].split('/')[-1]
		prop_datatype = p["datatype"]["value"].split('#')[-1]
		properties[prop_id] = prop_datatype
	return properties

properties = list_properties()
#properties["P56"] = "ExternalId"


def checkID (property, ID):
	query = 'SELECT ?item WHERE { ?item swdt:' + property + ' "' + ID + '" }'
	check_id = sparql(endpoint_scrap,query)
	result = check_id["results"]["bindings"]
	if len(result) == 0:
		return "create"
	elif len(result == 1):
		return pywikibot.ItemPage(repo,check_id["results"]["bindings"][0]["item"]["value"].split('/')[-1])

############ Funkce pro převod řetězce na QID ###########

def label2entity (type, string):
	if string != "":
		if type:
			queryType = f'?item swdt:P1 swd:{type}.'
		else:
			queryType = ""
		query = 'SELECT DISTINCT ?item WHERE { ' + queryType + ' ?item (rdfs:label|skos:altLabel) "' + string + '"@cs. }'
		result = sparql(endpoint_scrap, query)["results"]["bindings"]
		if len(result) == 1:
			return result[0]["item"]["value"].split('/')[-1]
		else:
			return None

def string2entity (property, string):
	if string != "":
		query = 'SELECT DISTINCT ?item WHERE { ?statement spq:P34 "' + string + '"; sps:' + property + ' ?item. }'
		result = sparql(endpoint_scrap, query)["results"]["bindings"]
		if len(result) == 1:
			return result[0]["item"]["value"].split('/')[-1]
		else:
			return None

def dict2entity (prop, string):
	replacements = {
		"P33": {
			r'^m': "Q70088",
			r'^[žf]': "Q70090"
		},
		"P64": {
			r'^(řím|röm)': "Q5998782",
			r'^(izr|isr|žid|jüd|mos)': "Q4505586",
			r'^(bez|konf|conf)': "Q5998781",
			r'^(advent)': "Q5998783",
			r'^(nekat|akat)': "Q5998784",
			r'^(anglik)': "Q5998785",
			r'^(českobr)': "Q5998786",
			r'^(čsl|českoslov|čslov)': "Q5998787",
			r'(aug|luter)': "Q5998788",
			r'(helv|kalv)': "Q5998789",
			r'^(evan|prot)': "Q5998796",
			r'^(metod)': "Q5998790",
			r'^(prav|ortod)': "Q5998791",
			r'^(řec|griech)': "Q5998792",
			r'^(sab)': "Q5998793",
			r'^(staro|alt)': "Q5998794",
			r'^(nežid)': "Q5998795"
		},
		"P67": {
			r'^(svob|led)': "Q5998775",
			r'^(žen|vdan|mar|verh)': "Q5998776",
			r'^(ovd|vdov|verw|wit)': "Q5998777",
			r'^(roz|gesch)': "Q5998778"
		},
		"P69": {
			r'^(č|tsch)': "",
			r'^(jid)': "Q5998800",
			r'^(an|en)': "Q5998801",
			r'^(něm|de)': "Q5998802",
			r'^(če|tsch)': "Q5998803",
			r'^(chor)': "Q5998804",
			r'^(fr)': "Q5998805",
			r'^(ma|hu)': "Q5998806",
			r'^(po)': "Q5998807",
			r'^(rum)': "Q5998808",
			r'^(rus[ií])': "Q5998809",
			r'^(ruš|russ)': "Q5998810",
			r'^(slo)': "Q5998811",
			r'^(uk)': "Q5998812"
		},
	}
	for pattern, entity in replacements[prop].items():
		if re.match(pattern, string, re.IGNORECASE):
			return entity
	return None

def add_claim_loc (item, data, locString, propItem, propString):
    locQ = string2entity(propItem, locString)
    if not locQ:
        locQ = label2entity("Q121436", locString)
    
    if locQ:
        data = add_claim (item, data, propItem, locQ, quals = [ [ "P34", locString ] ])
    else:
        data = add_claim (item, data, propString, locString)
        
    return data

############### Funkce pro editaci Wikibase ###############

def create_item (data, summ):
	new_item = pywikibot.ItemPage(repo)
	try:
		new_item.editEntity(data, summary=summ)
		labels = data.get("labels", {})
		label_value = labels.get("cs") or labels.get("de") or next(iter(labels.values()), "<bez labelu>")
		print(f'ID {label_value} neexistuje, vytvořeno: {new_item}')
	except pywikibot.exceptions.OtherPageSaveError as error:
		item_exist = re.search(r'\[\[Item:Q(\d+)\|Q\1\]\]',str(error)).group(1)
		new_item = pywikibot.ItemPage(repo,f'Q{item_exist}')
	return new_item

def get_statement_id(item, property, value, quals=None, restrictive=False, rank=None):
    if item != "create":
        if property in item.claims:
            for statement in item.claims[property]:
                target = statement.getTarget()

                # Check if the statement target matches the value
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
                    match_found = (statement_value == value)
                else:
                    match_found = False

                # If the target matches, check for qualifiers and rank
                if match_found:
                    # Check if the rank matches (if rank is provided)
                    if rank and statement.rank != rank:
                        continue  # Skip the statement if the rank doesn't match

                    # If qualifiers are provided, check them
                    if quals:
                        all_qualifiers_match = True

                        # Check if the statement contains all specified qualifiers
                        for qualifier_property, qualifier_value in quals:
                            if qualifier_property not in statement.qualifiers:
                                all_qualifiers_match = False
                                break

                            # Check if any of the qualifier values match
                            qualifier_match_found = False
                            for qualifier in statement.qualifiers[qualifier_property]:
                                qualifier_target = qualifier.getTarget()

                                # Match string, ItemPage, or WbTime qualifier values
                                if isinstance(qualifier_target, str) and qualifier_target == qualifier_value:
                                    qualifier_match_found = True
                                    break
                                elif isinstance(qualifier_target, pywikibot.page.ItemPage) and qualifier_target.getID() == qualifier_value:
                                    qualifier_match_found = True
                                    break
                                elif isinstance(qualifier_target, pywikibot.WbTime):
                                    if qualifier_target.precision == 11:
                                        qualifier_value_str = f"{qualifier_target.year}-{qualifier_target.month:02d}-{qualifier_target.day:02d}"
                                    elif qualifier_target.precision == 10:
                                        qualifier_value_str = f"{qualifier_target.year}-{qualifier_target.month:02d}"
                                    elif qualifier_target.precision == 9:
                                        qualifier_value_str = f"{qualifier_target.year}"

                                    if qualifier_value_str == qualifier_value:
                                        qualifier_match_found = True
                                        break

                            # If any qualifier doesn't match, break the loop
                            if not qualifier_match_found:
                                all_qualifiers_match = False
                                break

                        # Check if the statement has extra qualifiers (if restrictive=True)
                        if restrictive and all_qualifiers_match:
                            # The number of qualifiers must exactly match
                            if len(statement.qualifiers) != len(quals):
                                all_qualifiers_match = False

                        # If all qualifiers match (and restrictive condition is satisfied), return the statement ID (snak)
                        if all_qualifiers_match:
                            return statement.snak
                    else:
                        # No qualifiers provided, return the statement ID directly
                        return statement.snak

    return None


def add_claim (item, data, property, value, quals=None, restrictive=True, rank="normal"):
	if value != "":
		value = value.strip()
		if properties[property] == "Time":
			value = normal_dat(value)
		exist = get_statement_id(item, property, value, quals=quals, restrictive=restrictive, rank=rank)
		if exist == None:
			claim_data = {
				"mainsnak": {
					"snaktype": "value",
					"property": property,
					"datavalue": {}
					},
				"type": "statement",
				"rank": rank
			}
			if properties[property]	== "WikibaseItem":
				claim_data["mainsnak"]["datavalue"] = {
						"value": {
							"entity-type": "item",
							"numeric-id": value.replace("Q","")
						},
						"type": "wikibase-entityid"				
				}
			elif properties[property] in [ "String", "ExternalId", "Url", "url" ]:
				claim_data["mainsnak"]["datavalue"] = {
						"type": "string",
						"value": value
						}
			elif properties[property] == "Time":
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
							'calendarmodel': 'http://www.wikidata.org/entity/Q1985727',
							'timezone': 0,
							'after': 0,
							'before': 0
							},
						"type": "time"
						}
			if quals:
				claim_data["qualifiers"] = []
				for qual in quals:
					qual_data = add_qualifier (properties, qual)
					claim_data["qualifiers"].append(qual_data)
			data["claims"].append(claim_data)
	return data


def add_claim_amount ( item, ec, p, value, unit, summ ):
	valNormal = value.strip()
	qexist = []
	if p in ec["claims"]:
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			amount = val["mainsnak"]["datavalue"]["value"]["amount"]
			unit = val["mainsnak"]["datavalue"]["value"]["unit"].split('/')[-1]
			valJoin = amount + unit
			qexist.append(valJoin)
	valNewJoin = '+' + str(valNormal) + str(unit)
	if valNewJoin in qexist:
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			if val["mainsnak"]["datavalue"]["value"] == valNormal:
				return cl
	else:
		print("Vytvářím tvrzení "+p+"="+valNormal)
		claim = pywikibot.Claim(repo, p)
		unitForm = pywikibot.ItemPage(repo, unit)
		target = pywikibot.WbQuantity(site=repo, amount=valNormal, unit=unitForm)
		claim.setTarget(target)
		item.addClaim(claim, summary=summ)
		return claim

def add_claim_monoling ( item, ec, p, string, summ ):
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
		print("Vytvářím tvrzení "+p+"="+string)
		claim = pywikibot.Claim(repo, p)
		target = pywikibot.WbMonolingualText(string, "cs")
		claim.setTarget(target)
		item.addClaim(claim, summary=summ)
		return claim

def add_qualifier (properties, qual):
	qual_data = {
			"snaktype": "value",
			"property": qual[0],
		}
	if properties[qual[0]] == "WikibaseItem":
		qual_data["datavalue"] = {
			"value": {
				"entity-type": "item",
				"numeric-id": qual[1].replace("Q","")
				},
			"type": "wikibase-entityid"
		}
	elif properties[qual[0]] in [ "String", "ExternalId", "Url", "url" ]:
		qual_data["datavalue"] = {
			"value": qual[1],
			"type": "string"
			}
	elif properties[qual[0]] == "Time":
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
				'calendarmodel': 'http://www.wikidata.org/entity/Q1985727',
				'timezone': 0,
				'after': 0,
				'before': 0
				},
			"type": "time"
			}

	return qual_data

def add_qualifier_q ( claim, ec, p, q, summ):
	qexist = []
	val = claim.toJSON()
	if "qualifiers" in val and p in val["qualifiers"]:
		for qual in val["qualifiers"][p]:
			qexist.append("Q"+str(qual["datavalue"]["value"]["numeric-id"]))
	if q not in qexist:
		qualifier = pywikibot.Claim(repo, p)
		target = pywikibot.ItemPage(repo, q)
		qualifier.setTarget(target)
		claim.addQualifier(qualifier, summary="+qualifier")
	
def add_qualifier_str ( claim, ec, p, string, summ):
	strNormal = string.strip()
	qexist = []
	val = claim.toJSON()
	if "qualifiers" in val and p in val["qualifiers"]:
		for qual in val["qualifiers"][p]:
			qexist.append(qual["datavalue"]["value"])
	if strNormal not in qexist:
		qualifier = pywikibot.Claim(repo, p)
		qualifier.setTarget(strNormal)
		claim.addQualifier(qualifier, summary="+qualifier")
	#time.sleep(3)
	
def add_qualifier_dat ( claim, ec, p, string, summ):
	qexist = []
	val = claim.toJSON()
	if "qualifiers" in val and p in val["qualifiers"]:
		for qual in val["qualifiers"][p]:
			precision = qual["datavalue"]["value"]["precision"]
			if precision == 11:
				date = re.sub(r'.*(\d{4}-\d{2}-\d{2}).*',r'\1',qual["datavalue"]["value"]["time"])
			elif precision == 10:
				date = re.sub(r'.*(\d{4}-\d{2}).*',r'\1',qual["datavalue"]["value"]["time"])
			elif precision == 9:
				date = re.sub(r'.*(\d{4}).*',r'\1',qual["datavalue"]["value"]["time"])
			qexist.append(date)
	if string not in qexist:
		qualifier = pywikibot.Claim(repo, p)
		if re.match(r"\d{4}-\d{2}-\d{2}", string):
			timestamp = pywikibot.Timestamp.fromISOformat( string+"T00:00:00Z")
			target = pywikibot.WbTime.fromTimestamp(timestamp, precision=11)
		elif re.match(r"\d{4}-\d{2}", string):
			timestamp = pywikibot.Timestamp.fromISOformat( string+"-01T00:00:00Z")
			target = pywikibot.WbTime.fromTimestamp(timestamp, precision=10)
		elif re.match(r"\d{4}", string):
			timestamp = pywikibot.Timestamp.fromISOformat( string+"-01-01T00:00:00Z")
			target = pywikibot.WbTime.fromTimestamp(timestamp, precision=9)
		qualifier.setTarget(target)
		claim.addQualifier(qualifier, summary="+qualifier")
	#time.sleep(3)

def remove_claim (item, data, property, value, quals=None, restrictive=False, rank=None):
	exist = get_statement_id(item, property, value, quals=quals, restrictive=restrictive, rank=rank)
	if exist:
		remove_data = {
			"id": exist,
			"remove": ""
		}
		data["claims"].append(remove_data)
	return data

def remove_claim_id (item, data, id):
	remove_data = {
		"id": id,
		"remove": ""
	}
	data["claims"].append(remove_data)
	return data

def remove_claim_q ( item, ec, p, q, summ ):
	qexist = []
	if p in ec["claims"]:
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			qexist.append("Q"+str(val["mainsnak"]["datavalue"]["value"]["numeric-id"]))
	if q in qexist:
#		print("Entita již obsahuje tvrzení "+p+"="+strNormal)
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			if val["mainsnak"]["datavalue"]["value"]["numeric-id"] == int(re.sub('Q','',q)):
				print("Odstraňuji tvrzení "+p+"="+q)
				item.removeClaims(cl, summary=summ)
				
def remove_claim_str ( item, ec, p, string, summ ):
	strNormal = string.strip()
	qexist = []
	if p in ec["claims"]:
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			qexist.append(val["mainsnak"]["datavalue"]["value"])
	if strNormal in qexist:
#		print("Entita již obsahuje tvrzení "+p+"="+strNormal)
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			if val["mainsnak"]["datavalue"]["value"] == strNormal:
				print("Odstraňuji tvrzení "+p+"="+strNormal)
				item.removeClaims(cl, summary=summ)
				
def remove_claim_dat ( item, ec, p, string, summ ):
	strNormal = string.strip()
	qexist = []
	if p in ec["claims"]:
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			date = re.sub(r'.*(\d{4}-\d{2}-\d{2}).*',r'\1',val["mainsnak"]["datavalue"]["value"]["time"])
			qexist.append(date)
	if strNormal in qexist:
#		print("Entita již obsahuje tvrzení "+p+"="+strNormal)
		for cl in ec["claims"][p]:
			val = cl.toJSON()
			if re.sub(r'.*(\d{4}-\d{2}-\d{2}).*',r'\1',val["mainsnak"]["datavalue"]["value"]["time"]) == strNormal:
				print("Odstraňuji tvrzení "+p+"="+strNormal)
				item.removeClaims(cl, summary=summ)


def remove_qualifier_str ( claim, ec, p, string, summ):
	strNormal = string.strip()
	if p in claim.qualifiers:
		for qual in claim.qualifiers[p]:
			if qual.getTarget() == strNormal:
				claim.removeQualifier(qual, summary=summ)
				
def add_ref ( claim, link, summ):
	# https://www.wikidata.org/wiki/Wikidata:Pywikibot_-_Python_3_Tutorial/Setting_sources
#	print("Přidávám referenci")
	try:
		srcs = claim.getSources()
	except:
		srcs = []
		
#	for src in srcs:
#		print(src)
#		if "P48" in scr:
#			print(src)
	claimJSON = claim.toJSON()
	new_ref = pywikibot.Claim(repo,"P48")
	new_ref.setTarget(link)
	
	addRef = True
	if "references" in claimJSON:
		refs = [ ref["snaks"]["P48"][0]["datavalue"]["value"]["numeric-id"] for ref in claimJSON["references"] if "P48" in ref["snaks"] ]
		numID = int(re.sub(r'.*Q([0-9]+)\]\]',r'\1',str(link)))
		if numID in refs:
			addRef = False
#			print('Tvrzení již obsahuje danou referenci')
	if addRef == True:
		claim.addSource(new_ref, summary=u'+ zdroj')
		print('Reference přidána')
		

import time
from SPARQLWrapper import JSON, SPARQLWrapper

############### SPARQL funkce ###############

endpoint_src = 'https://src.daelba.eu/sparql'
endpoint_scrap = 'https://scrap.daelba.eu/sparql'
endpoint_wd = 'https://query.wikidata.org/sparql'
endpoint_fg = 'https://database.factgrid.de/sparql'
endpoint_gotha = 'https://gotha.wikibase.cloud/query/sparql'


def sparql(endpoint, query):
    user_agent = "GothaDownloader/1.0 (baranek@hiu.cas.cz)"
    sparql = SPARQLWrapper(endpoint, agent=user_agent)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    while True:
        try:
            return sparql.query().convert()
        except Exception as error:
            print(error)
            print("\nDotaz na SPARQL endpoint se nezdařil. Opakuji...")
            time.sleep(5)
            continue


def get_bigData(endpoint, query):
    items = []
    offset = 0

    while True:
        print(f'Offset: {offset}')
        query_offset = query + '''
        LIMIT 10000
        OFFSET ''' + str(offset)

        result = sparql(endpoint, query_offset)["results"]["bindings"]
        if len(result) != 0:
            items.extend(result)
            offset += 10000
        else:
            print('Dohledáno ' + str(len(items)) + ' výsledků')
            return items

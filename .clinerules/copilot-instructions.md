# Copilot Instructions for LOD

# Jazyk
- Při komunikaci používej češtinu, ale jinak kód a dokumentaci piš v angličtině.

# Komunikace
- Pokud máš otázku, polož ji. Nehádej, co uživatel chce, pokud to není jasné.
- Pokud uživatel napíše zadání, jakoby bylo jednoduché, ale tobě připadá složité, zeptej se na detaily. Uživatel často může poskytnout jednoduchou informaci nebo cestu k řešení, která ti pomůže.
- Počítej s tím, že uživatel není profesionální programátor a nezná klasické standardy. Pokud uživatel navrhuje nějaké nestandardní řešení, upozorni jej na to a vysvětli lepší alternativy.

# Konfigurace balíčku
## Klíčový koncept: `LOD_CONFIG_MODULE` environment variable

Balíček `lod` podporuje flexibilní konfiguraci přes `LOD_CONFIG_MODULE` env var. Toto umožňuje:
- **Centralizovanou konfiguraci** v projektech, které `lod` používají (ne v samotném `lod` kořenu)
- **Kontejnerové nasazení** — snadné nastavení v Docker Compose/Kubernetes proměnnými
- **Monorepo support** — každý service má vlastní config modul

Priority hledání konfigurace:
1. `LOD_CONFIG_MODULE` env var (custom modul) — z balíčků mimo lod
2. `lod_config` fallback — klasický přístup (zpětná kompatibilita)
3. `None` — žádná custom konfigurace (default endpoints se používají)

Key files:
- `lod/config_loader.py` — hlavní logic pro prioritizované načítání configurace
- `lod/endpoints.py` — používá `config_loader.load_config()` místo přímého importlib
- `lod/wikibase.py` — totéž
- `tests/test_config_loader.py` — 5 testů pokrývajících všechny scenáře

## Implementační poznámky
- Logging vždy indikuje, odkud se konfigurace načetla (DEBUG/INFO level)
- Error handling je srozumitelný (ImportError s kontextem, když `LOD_CONFIG_MODULE` neexistuje)
- Zpětná kompatibilita: projekty bez `LOD_CONFIG_MODULE` fungují bez změn

## Prefixy Wikibase (aktuální strategie)
- Prefixy pro SPARQL už nejsou nastavovány přes `WIKIBASE_PREFIX_*`.
- Používej pouze dvojici `WIKIBASE_PROJECT_CODE` + `WIKIBASE_HOST` (resp. `LOD_` env varianty).
- Prefix aliases se generují jako `{PROJECT_CODE}_wd`, `{PROJECT_CODE}_wdt`, `{PROJECT_CODE}_pq`, `{PROJECT_CODE}_ps`.
- V dotazech se PREFIX deklarace skládají automaticky; nevracet se k legacy override režimu.

## Nové moduly (v0.4.0)

### `lod.errors` — Error handling
- Hierarchie výjimek: `LODError`, `SPARQLError`, `RateLimitError`, `AuthenticationError`, `EntityNotFoundError`, `ValidationError`, `NetworkError`
- `RetryConfig` dataclass pro konfiguraci retry logiky s exponenciálním backoff
- Všechny SPARQL a REST operace používají tuto error handling logiku

### `lod.rest` — RESTful API Client
- `WikibaseRESTClient` — async HTTP klient pro Wikibase MediaWiki API
- Metody: `get_item()`, `get_property()`, `get_entity()`, `search_entities()`, `create_item()`, `create_property()`, `set_label()`, `set_description()`, `set_claim()`, `delete_entity()`
- Automatická retry logika při rate limit (429) a server chybách (5xx)
- Podpora API token autentizace pro write operace

### `lod.validation` — Entity ID validace
- `validate_qid()`, `validate_pid()`, `validate_entity_id()` — validace formátu
- `parse_entity_uri()` — parsování URI do (type, id) tuple
- `normalize_uri()` — normalizace entity/property ID na plné URI
- `extract_entity_id()` — extrakce entity ID z různých formátů (prefixy, závorky, URI)

### `lod.endpoints` — Async SPARQL podpora
- `sparql_async()` — async verze `sparql()` funkce
- `bigData_async()` — async generator pro paginované velké výsledky
- `batch_iterate()` — utility pro batch zpracování

# Wikibase editační helpery (neaktuálnější změny)

## `lod/wikibase.py`

### Batch API styl
- Editace entit se typicky připravují jako změny v `data["claims"]` listu a pak se aplikují přes `item.editEntity(data, summary=...)`.
- Odstranění claimu se provádí přidáním `{"id": <statement_id>, "remove": ""}` do `data["claims"]`.

### Nové helper funkce

#### `remove_property(item, data, property)`
- Odstraní **všechna** tvrzení dané vlastnosti z entity.
- Bezpečně vrací `data` nezměněné, pokud `item == "create"` nebo vlastnost nemá tvrzení.

#### `_get_claim_value(statement, include_unit=True)`
- Pomocná funkce pro extrakci porovnatelné hodnoty z pywikibot `Claim.getTarget()`.
- Podporuje: `str`, `ItemPage` (vrací ID), `WbMonolingualText` (vrací `.text`), `WbTime` (podle přesnosti `YYYY-MM-DD`, `YYYY-MM`, `YYYY`) a `WbQuantity` (vrací `amount` případně `amountQ<unit_id>`).
- Pro `WbQuantity` je `include_unit=True` vrací `"<amount>Q<unit_id>"`, `include_unit=False` vrací jen `"<amount>"`. To se používá pro shodu podle částky bez ohledu na jednotku.
- Tuto funkci používá i `get_statement_id` pro porovnání mainsnak i qualifier hodnot.

#### `get_statement_id(item, property, value, quals=None, restrictive=False, rank=None)`
- Najde ID existujícího statementu podle hodnoty a volitelně kvalifikátorů/ranku.
- Pro quantity automaticky detekuje, zda `value` obsahuje jednotku (`"500Q11573"` vs `"500"`), a podle toho porovnává s jednotkou nebo jen částku.
- Pro kvalifikátory používá stejnou hodnotovou logiku jako pro hlavní hodnotu.

#### `update_unique_property(item, data, property, value, quals=None, rank="normal", unit=None)`
- Aktualizuje vlastnost, která může mít jen jednu hodnotu.
- Postup:
  1. Pokud `value == ""`, vrátí `data` nezměněné (prázdnou hodnotu neukládá).
  2. Najde první existující statement s hodnotou odpovídající nové pomocí `_get_claim_value`.
  3. Pokud takový statement existuje, ponechá přesně jeden (první nalezený) a odstraní všechny ostatní statementy té vlastnosti — včetně duplicit se stejnou hodnotou. Nové tvrzení nepřidává.
  4. Pokud žádný statement s novou hodnotou neexistuje, odstraní všechna existující tvrzení a přidá nové tvrzení. Protože `remove_property` pouze zaznamenává odstranění do `data["claims"]` a nemění `item.claims`, použije se pro volání `add_claim` dočasný item s vyprázdněnou vlastností, aby `add_claim` neviděla staré hodnoty a nové tvrzení skutečně přidala.
- Parametry `quals`, `rank`, `unit` se předávají do `add_claim`.

# Hlavní architektonické změny (v0.5.0 unreleased)

## `lod.claim_builder.ClaimBuilder`
- Centralizuje konstrukci datových bloků pro Wikibase `editEntity` batch API.
- Podporuje datové typy: `WikibaseItem`, `String`, `ExternalId`, `Url`, `Monolingualtext`, `Time`, `Quantity`.
- Sjednocuje kvalifikátory i reference do jednoho claim dictu.
- Reference lze zadat jako tuple `(property_id, value)` nebo dict `{"property": ..., "value": ...}`.
- Pro Quantity používej `unit` parametr; builder vytvoří správný `amount` + `unit` blok.

## `lod.date_normalizer.DateNormalizer`
- Refaktorováno z původní `normal_dat` v `lod/wikibase.py`.
- Defaultně **neprovádí** konverzi římských číslic (`roman_numerals=False`) — používej jen pokud víš, že vstup skutečně obsahuje římská čísla.
- Stará `normal_dat` zachována pro zpětnou kompatibilitu, ale nový kód by měl používat `DateNormalizer`.

## `lod.wikibase_client.WikibaseClient`
- Nový stateful klient místo globálního mutable stavu v `lod/wikibase.py`.
- Zapouzdřuje konfiguraci, lazy inicializaci `site`/`repo`, cache vlastností, prefix block a SPARQL/edit helpery.
- `lod.wikibase` nyní deleguje `site`/`repo`/`properties` na výchozí instanci `WikibaseClient`, ale veškerý veřejný API zůstává zachován.
- Preferuj `WikibaseClient` pro nový kód; module-level helpery jsou legacy-friendly wrapper.

## Validace vstupů v `lod.wikibase`
- Všechny veřejné helpery validují property/item ID přes `lod.validation`.
- Neplatné ID vyhodí `ValidationError` místo poškozeného SPARQL/API payloadu.
- Testy v `tests/test_wikibase_validation.py` pokrývají `checkID`, `string2entity`, `label2entity`, `add_claim`, `add_claim_loc`, `remove_claim`, `remove_property`, `update_unique_property`, `get_statement_id`.

## Odstraněné legacy helpery
- `add_qualifier_q`, `add_qualifier_str`, `add_qualifier_dat`, `remove_claim_q`, `remove_claim_str`, `remove_claim_dat`, `remove_qualifier_str` již neprovádějí přímé mutace `Claim`/`ItemPage`.
- Místo toho vyhodí `DeprecationError` s odkazem na batch `data["claims"]` API (`item.editEntity(data, summary=...)`).
- Pro odstranění claimu použij `{"id": <statement_id>, "remove": ""}` v `data["claims"]`.

## `update_unique_property` a Quantity srovnání
- Srovnání Quantity nyní bere v úvahu jednotku jen pokud je explicitně zadána (`"500Q11573"` vs `"500"`).
- Pokud existuje statement se shodnou hodnotou, ponechá se přesně jeden a odstraní se duplicity; nový claim se nepřidává.
- Pokud neexistuje, použije se dočasný item s vyprázdněnou vlastností, aby `add_claim` neviděla staré hodnoty.

## Caching a konfigurace
- `_ensure_properties` cachuje seznam vlastností na 5 minut; invalidace přes `refresh_properties()`.
- `_wikibase_prefix_block` cachuje PREFIX deklarace pro danou kombinaci `WIKIBASE_PROJECT_CODE` + `WIKIBASE_HOST`.
- `_cfg_value` nově podporuje `LOD_` prefix u environment variables.
- Chybějící konfigurace vyhodí `ConfigurationError` místo `RuntimeError`.

# Ukončení sezení
- Pokud uživatel napíše "ukonči session" nebo "ukonči sezení": a) aktualizuj dokumentaci, b) dopiš do instrukcí pro copilota hlavní body, které zabraly nejvíce přemýšlení, c) aktualizuj CHANGELOG, d) připrav commit.
- Pokud uživatel napíše "vytvoř verzi", udělej totéž jako při "ukonči session" a navíc commit taguj ho jako "vX.Y.Z" (závisí na tom, jestli jde o patch, minor nebo major release).

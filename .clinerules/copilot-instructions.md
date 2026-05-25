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

# Ukončení sezení
- Pokud uživatel napíše "ukonči session" nebo "ukonči sezení": a) aktualizuj dokumentaci, b) dopiš do instrukcí pro copilota hlavní body, které zabraly nejvíce přemýšlení, c) aktualizuj CHANGELOG, d) připrav commit.
- Pokud uživatel napíše "vytvoř verzi", udělej totéž jako při "ukonči session" a navíc commit taguj ho jako "vX.Y.Z" (závisí na tom, jestli jde o patch, minor nebo major release).
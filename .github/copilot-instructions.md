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

# Ukončení sezení
- Pokud uživatel napíše "ukonči session" nebo "ukonči sezení": a) aktualizuj dokumentaci, b) dopiš do instrukcí pro copilota hlavní body, které zabraly nejvíce přemýšlení, c) aktualizuj CHANGELOG, d) připrav commit.
- Pokud uživatel napíše "vytvoř verzi", udělej totéž jako při "ukonči session" a navíc commit taguj ho jako "vX.Y.Z" (závisí na tom, jestli jde o patch, minor nebo major release).
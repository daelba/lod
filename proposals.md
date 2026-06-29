# Návrhy na refaktorizaci a zlepšení `lod/wikibase.py`

> Stav k datu 27. 6. 2026. Návrh vychází z aktuálního `lod/wikibase.py` a jeho vztahu k modulům `lod/endpoints.py`, `lod/errors.py`, `lod/validation.py` a `lod/rest.py`.
>
> **Legenda stavu:**
> - ✅ **Implementováno** – změna je již v kódu a prochází testy.
> - 🔄 **Částečně implementováno** – základní varianta je hotová, ale plná podoba vyžaduje další práci.
> - ⏳ **Návrh** – zatím neimplementováno, čeká na rozhodnutí/prioritu.
>
> **Poslední implementovaná fáze:** Odstranění legacy pywikibot helperů a jejich nahrazení `DeprecationError` (kapitola 2.4 a fáze 10).

---

## 1. Shrnutí aktuálního stavu

Soubor `lod/wikibase.py` je monolitický modul (cca 600 řádků), který zastřešuje několik různých oblastí odpovědnosti:

1. **Konfigurace Wikibase** – načítání `WIKIBASE_*` proměnných, sestavování prefixů.
2. **SPARQL helpery** – `list_properties`, `check_by_label_desc`, `checkID`, `label2entity`, `string2entity`.
3. **Normalizace vstupů** – zejména `normal_dat` pro datumy.
4. **Editace entit přes pywikibot** – `create_item`, `add_claim`, `add_qualifier*`, `remove_*`, `update_unique_property`.
5. **Porovnávání hodnot** – `_get_claim_value`, `get_statement_id`.

Modul funguje, ale má řadu architektonických a udržovatelských problémů. Níže jsou navrženy možnosti zlepšení rozdělené do kategorií.

---

## 2. Refaktorizace a abstrakce

### ✅ 2.1 Odstranění globálního stavu – `WikibaseClient`

Aktuálně modul drží globální proměnné `site`, `repo`, `properties` a inicializuje je přes `_ensure_site_repo()` / `_ensure_properties()`. To ztěžuje testování, vede k vedlejším efektům a neumožňuje práci s více Wikibase instancemi najednou.

**Návrh:** Zavést třídu `WikibaseClient`, která zapouzdří:

- konfiguraci (`project_code`, `host`, `endpoint_key`, `site_code`, `site_family`),
- lazy inicializaci `site` / `repo` přes `@functools.cached_property`,
- cachovaný seznam vlastností s možností invalidace,
- metodu pro získání SPARQL endpointu.

```python
from functools import cached_property
from typing import Optional
import pywikibot

from .endpoints import get_endpoint
from .config_loader import load_config

class WikibaseClient:
    def __init__(self, config: Optional[object] = None):
        self._cfg = config or load_config()

    @cached_property
    def repo(self) -> pywikibot.DataSite:
        site_code = self._require("WIKIBASE_SITE_CODE")
        family = self._require("WIKIBASE_SITE_FAMILY")
        return pywikibot.Site(site_code, family).data_repository()

    @cached_property
    def properties(self) -> dict[str, str]:
        return self._load_properties()

    def sparql_endpoint(self) -> str:
        return get_endpoint(self._require("WIKIBASE_ENDPOINT_KEY"))

    def _require(self, name: str) -> str:
        value = os.getenv(name) or getattr(self._cfg, name, None)
        if not value:
            raise ConfigurationError(f"Missing {name}")
        return value
```

**Přínos:**
- Žádný globální mutable stav.
- Možnost vytvořit více klientů pro různé instance.
- Snadnější mockování v testech.

**Stav:** Implementováno – nový modul `lod/wikibase_client.py` obsahuje třídu `WikibaseClient`. Modul `lod/wikibase.py` nyní používá default klienta pro `_ensure_site_repo`, `_ensure_properties`, `refresh_properties` a zachovává zpětnou kompatibilitu. Přidány testy v `tests/test_wikibase_client.py`.

### ⏳ 2.2 Bezpečné sestavování SPARQL prefixů a literálů

Aktuálně se literály vkládají do SPARQL přímo pomocí `_escape_sparql_literal`. To je křehké a stále zranitelné např. při špatně escapovaných uvozovkách.

**Návrh:** Ponechat přímé psaní SPARQL dotazů (požadavek zadavatele). Zlepšení se zaměří na:

- Pomocnou funkci `_with_wikibase_prefixes(query)` přesunout do `WikibaseClient` a cachovat prefix block.
- Vytvořit robustnější `_escape_sparql_literal`, který pokrývá všechny znaky vyžadované SPARQL specifikací (např. `\t`, `\r`, backslash, uvozovky).
- Doporučit konvenci psát dotazy jako f-stringy s explicitním escapováním každého externího vstupu:

```python
query = client.with_prefixes(
    f'SELECT ?item WHERE {{ ?item rdfs:label {client.literal(label)}@cs . }}'
)
```

**Přínos:**
- Zachová se přímá kontrola nad SPARQL.
- Zmenší se riziko chyb při escapování.
- Prefixy se generují konzistentně a efektivně.

### ✅ 2.3 Centralizace tvorby claimů – `ClaimBuilder`

Logika pro datové typy `WikibaseItem`, `String`, `ExternalId`, `Url`, `Monolingualtext`, `Time`, `Quantity` byla rozptýlená mezi `add_claim`, `add_qualifier_data` a `add_qualifier_*`. Opakovala se zejména logika pro `Time`.

**Návrh:** Vytvořit `ClaimBuilder`, který převezme property type, hodnotu a parametry, a vrátí hotový JSON pro batch API.

```python
class ClaimBuilder:
    def __init__(self, properties: dict[str, str], host: str):
        self.properties = properties
        self.host = host

    def build(self, property_id: str, value, *, rank="normal", unit=None, language="cs") -> dict:
        prop_type = self.properties.get(property_id)
        if prop_type is None:
            raise ValidationError(f"Unknown property: {property_id}")
        builder = self._DISPATCH.get(prop_type, self._build_string)
        return builder(property_id, value, rank=rank, unit=unit, language=language)

    def _build_time(self, property_id, value, **kwargs) -> dict: ...
    def _build_quantity(self, property_id, value, *, unit, **kwargs) -> dict: ...
    def _build_item(self, property_id, value, **kwargs) -> dict: ...
```

**Přínos:**
- Jeden zdroj pravdy pro datové typy.
- Snazší přidání nového typu (např. `GlobeCoordinate`).
- Lepší testovatelnost.

**Stav:** Implementováno – nový modul `lod/claim_builder.py` obsahuje `ClaimBuilder` a `build_claim_key`. `add_claim` a `add_qualifier_data` nyní používají `ClaimBuilder`. Přidány unit testy `tests/test_claim_builder.py`.

### ✅ 2.4 Odstranění legacy pywikibot helperů

Funkce jako `add_qualifier_q`, `add_qualifier_str`, `add_qualifier_dat`, `remove_claim_q`, `remove_claim_str`, `remove_claim_dat` (a dále `remove_qualifier_str`) pracovaly přímo s pywikibot objekty, duplikovaly logiku a nebyly konzistentní s novým batch API. Nový kód by měl používat batch `editEntity` formát nebo REST API (`lod.rest`).

**Návrh:**
- Těla funkcí byla **nahrazena** výjimkou `DeprecationError` (podtřídou `LODError`).
- Chybová hláška obsahuje jasný návod na náhradu.

Příklad chybové hlášky:

```
add_qualifier_q() was removed. Use add_claim(item, data, property, value, quals=[(p, value)]) + item.editEntity(data, summary=...) instead.
```

- Hlavní veřejné API zůstane v `lod/wikibase.py` jako tenká fasáda nad `WikibaseClient`.
- Pro komplexní scénáře je k dispozici `lod/wikibase_client.py` s novým API.

**Přínos:**
- Menší udržovací zátěž.
- Jasný směr pro uživatele knihovny.
- Eliminace duplicitní logiky.

**Stav:** Implementováno – `DeprecationError` byla přidána do `lod/errors.py`, legacy helpery v `lod/wikibase.py` nyní okamžitě vyhazují tuto výjimku s návodem na náhradu. Přidány testy v `tests/test_legacy_deprecation.py`.

---

## 3. Optimalizace

### ✅ 3.1 Cachování `list_properties()`

Seznam vlastností se mění zřídka. Aktuálně se načítá při každém volání `_ensure_properties()`.

**Návrh:**
- Cachovat výsledek v `WikibaseClient.properties` s TTL (např. 5 minut).
- Přidat metodu `refresh_properties()` pro explicitní invalidaci.

**Stav:** Implementováno – v `lod/wikibase.py` byl přidán TTL cache `_properties_cache` s výchozí platností `_PROPERTIES_CACHE_TTL_SECONDS = 300`. Dostupná je i funkce `refresh_properties()` pro ruční invalidaci cache. Přidány testy v `tests/test_wikibase.py`.

### ✅ 3.2 Předpočítaný prefix block

`_wikibase_prefix_block()` se volá před každým dotazem a opakovaně sestavuje string.

**Návrh:**
- Uložit prefix block jako atribut `WikibaseClient` po prvním použití.
- Použít `functools.lru_cache` na `_wikibase_prefix_block` (proměnné jsou odvozeny z konfigurace).

**Stav:** Implementováno – `_wikibase_prefix_block` nyní ukládá výsledek do slovníku `_prefix_block_cache` klíčovaného dvojicí `(project_code, host)`. Opakovaná volání vracejí ten samý string. Přidány testy v `tests/test_wikibase.py`.

---

## 4. Nové funkcionality

### ⏳ 4.1 Async varianty SPARQL helperů

`lod/endpoints.py` již obsahuje `sparql_async` a `bigData_async`. `wikibase.py` je zatím plně synchronní.

**Návrh:** Přidat async metody do `WikibaseClient`:

- `async_check_by_label_desc`
- `async_label2entity`
- `async_string2entity`
- `async_list_properties`

### ✅ 4.2 Podpora referencí v `add_claim`

Aktuálně `add_claim` nepodporovalo přidání reference ke claimu. `add_ref` existuje, ale pracuje s pywikibot objekty.

**Návrh:** Rozšířit `ClaimBuilder`/`WikibaseClient.add_claim` o parametr `references`:

```python
client.add_claim(
    item,
    property="P1",
    value="Q2",
    references=[
        {"property": "P48", "value": "Q123"},
        {"property": "P854", "value": "https://example.org"},
    ],
)
```

**Implementace:**
- `ClaimBuilder.build_claim` nyní přijímá volitelný parametr `references`.
- Podporované formáty:
  - Seznam dvojic `[(property_id, value), ...]`.
  - Seznam slovníků `[{"property": "P48", "value": "Q123"}, ...]`.
  - Slovníkový zápis `{property_id: value, ...}` pro jednu referenci.
- `add_claim` přijímá `references` a předává je builderu; reference se seskupí do jednoho Wikibase reference bloku.
- Podporovány jsou všechny datové typy, které `ClaimBuilder` zná (item, string, URL, time, quantity).

**Přínos:**
- Reference lze přidávat přímo v rámci batch `editEntity` payloadu.
- Není nutné používat legacy `add_ref` s pywikibot objekty.
- Konzistentní API s kvalifikátory.

**Stav:** Implementováno – přidány testy v `tests/test_claim_builder.py` a `tests/test_wikibase.py`.

### ⏳ 4.3 Hromadné operace s batchingem

Pro importy velkého množství dat by bylo užitečné mít batch editaci.

**Návrh:** Přidat `BatchEditor`:

```python
async with client.batch_editor() as editor:
    for record in records:
        editor.stage_create(label=record.label, claims=record.claims)
    results = await editor.commit(batch_size=50)
```

### ⏳ 4.4 Volitelný backend: pywikibot vs REST API

`lod/rest.py` poskytuje async REST klienta, ale není nikde použit. `wikibase.py` je zcela vázán na pywikibot.

**Návrh:**
- Umožnit ve `WikibaseClient` zvolit backend (`"pywikibot"` nebo `"rest"`).
- Pro základní operace (`get_item`, `set_label`, `set_claim`) používat společné rozhraní.
- REST backend by byl vhodný pro operace, kde pywikibot není dostupný nebo je pomalý.

### ✅ 4.5 Lepší normalizace datumů

`normal_dat` obsahoval heuristickou převodní tabulku římských číslic (`I` → `01`, `V` → `05` atd.), což mohlo vést k chybným výsledkům (např. text obsahující písmeno "V" se změnilo na "05").

**Návrh:**
- Vytvořit konfigurovatelný `DateNormalizer` s podporou více formátů.
- Římské číslice izolovat do samostatného volitelného pluginu.
- Přidat podporu pro ISO 8601, české formáty (`1. 5. 2024`) a neurčitá data (`2024`, `2024-05`).

```python
class DateNormalizer:
    def __init__(self, roman_numerals: bool = False):
        self.roman_numerals = roman_numerals

    def normalize(self, value: str) -> str: ...
```

**Stav:** Implementováno – nový modul `lod/date_normalizer.py` obsahuje `DateNormalizer` s volitelnými římskými číslicemi. `normal_dat` v `lod/wikibase.py` zachovává legacy chování (římské číslice zapnuté) pro zpětnou kompatibilitu. Přidány testy `tests/test_date_normalizer.py` a kontrola v `tests/test_wikibase.py`.

### ✅ 4.6 Validace vstupů pomocí `lod.validation`

Aktuálně se IDčka (QID, PID) validovaly ad-hoc nebo vůbec.

**Návrh:** Ve všech veřejných funkcích použít `validate_qid`, `validate_pid`, `validate_entity_id` z `lod.validation`. Při neplatném vstupu vyhodit `ValidationError`.

**Implementace:**
- Přidány interní helpery `_validate_pid` a `_validate_qid` do `lod/wikibase.py`.
- Validovány parametry v `checkID`, `string2entity`, `label2entity`, `add_claim_loc`, `get_statement_id`, `add_claim`, `remove_claim`, `remove_property` a `update_unique_property`.
- Při neplatném PID/QID se okamžitě vyhodí `ValidationError` místo vytvoření poškozeného SPARQL dotazu nebo API payloadu.

**Přínos:**
- Včasná detekce chyb na straně klienta.
- Prevence SPARQL syntaktických chyb a nebezpečných payloadů.
- Konzistentní chybové hlášky napříč knihovnou.

**Stav:** Implementováno – přidány testy v `tests/test_wikibase_validation.py`.

---

## 5. Bezpečnost a robustnost

### ✅ 5.1 Použití vlastních výjimek z `lod.errors`

V `wikibase.py` se stále používá `RuntimeError` (např. v `_require_cfg`). Projektní konvence zavádí `LODError`, `ValidationError`, `EntityNotFoundError`, `NetworkError`, `SPARQLError`.

**Návrh:**
- `_require_cfg` → `ConfigurationError` (nová podtřída `LODError`).
- Chyby SPARQL → `SPARQLError` s query a endpointem.
- Neznámá entita → `EntityNotFoundError`.

**Stav:** Implementováno pro `_require_cfg` – nová `ConfigurationError` v `lod/errors.py`, použita místo `RuntimeError`. Zbývá rozšířit použití `SPARQLError`, `EntityNotFoundError` a dalších výjimek i na SPARQL helpery a editaci entit.

### ✅ 5.2 Oprava `create_item`

Aktuální kód:

```python
item_exist = re.search(r"\[\[Item:Q(\d+)\|Q\1\]\]", str(error)).group(1)
```

Pokud regex nenajde shodu, volání `.group(1)` vyhodí `AttributeError` a původní chyba se ztratí.

**Návrh:**

```python
match = re.search(r"\[\[Item:Q(\d+)\|Q\1\]\]", str(error))
if match:
    item_id = match.group(1)
    return pywikibot.ItemPage(repo_obj, f"Q{item_id}")
raise EntitySaveError(f"Failed to create item: {error}") from error
```

**Stav:** Implementováno – regex match se nyní kontroluje před `.group(1)`; původní výjimka se zachová při neznámém formátu chyby.

### ✅ 5.3 Oprava porovnávání Quantity v `update_unique_property`

`update_unique_property` porovnává `_get_claim_value(statement)` (může obsahovat jednotku) s `value` (bez jednotky). To může způsobit, že se stávající hodnota nenajde a vytvoří se duplicitní statement.

**Návrh:** Sjednotit porovnávací klíč v celém modulu – používat `ClaimKey(value, unit, qualifiers)`.

**Stav:** Implementováno – srovnávací klíč s jednotkou se sestavuje pouze pro Quantity vlastnosti, pokud je zadána jednotka.

---

## 6. Testovatelnost a kompatibilita

### 🔄 6.1 Zachování zpětné kompatibility

Mnoho projektů závisí na volání `lod.wikibase.create_item`, `add_claim` atd. Návrhy by neměly tato API zlomit.

**Návrh:**
- `lod/wikibase.py` zůstane jako tenká fasáda nad `WikibaseClient`.
- Stávající funkce budou delegovat na novou implementaci.
- Legacy helpery budou odstraněny a nahrazeny výjimkou s návodem na náhradu.

**Stav:** Částečně implementováno – dosavadní veřejné API zůstává zachováno. Při plném refaktoringu na `WikibaseClient` bude nutné zachovat tenkou fasádu `lod/wikibase.py`.

### 🔄 6.2 Unit testy bez živého Wikibase

Nová architektura by měla umožňovat snadné mockování:

```python
class FakeRepo:
    def __init__(self, claims=None):
        self.claims = claims or {}

client = WikibaseClient(config=FakeConfig())
client._repo = FakeRepo()
```

Doporučuji přidat testy pro:
- `ClaimBuilder` pro všechny datové typy,
- `SparqlQueryBuilder` (kontrola escapování a prefixů),
- `DateNormalizer`,
- `update_unique_property` včetně edge cases.

**Stav:** Částečně – existují samostatné testy pro `ClaimBuilder` (`tests/test_claim_builder.py`) a `DateNormalizer` (`tests/test_date_normalizer.py`). Chybí testy pro `SparqlQueryBuilder`, který ještě neexistuje.

---

## 7. Navrhované implementační fáze

| Fáze | Popis | Priorita | Stav |
|------|-------|----------|------|
| 1 | Zavedení `WikibaseClient` a odstranění globálního stavu `site`/`repo`/`properties`. | Vysoká | ✅ |
| 2 | Použití výjimek z `lod.errors` místo `RuntimeError`; oprava `create_item`. | Vysoká | ✅ částečně (5.1, 5.2) |
| 3 | Vytvoření `SparqlQueryBuilder` s parametrizovanými literály a prefixy. | Vysoká | ⏳ |
| 4 | Vytvoření `ClaimBuilder` a centralizace datových typů. | Střední | ✅ |
| 5 | Cachování `properties` a prefix blocku. | Střední | ✅ |
| 6 | Přidání async variant SPARQL helperů. | Střední | ⏳ |
| 6a | Validace vstupů pomocí `lod.validation`. | Střední | ✅ |
| 7 | Podpora referencí v `add_claim`. | Nízká | ✅ |
| 7a | Hromadné editace (`BatchEditor`). | Nízká | ⏳ |
| 8 | Integrace REST API backendu z `lod.rest`. | Nízká | ⏳ |
| 9 | Refactoring `normal_dat` do `DateNormalizer`. | Nízká | ✅ |
| 10 | Odstranění legacy helperů a nahrazení výjimkou s návodem. | Nízká | ✅ |

---

## 8. ✅ Doporučení k okamžitému zásahu

Bez čekání na velký refaktoring byly provedeny následující bezpečné a rychlé opravy:

1. **Opravit `create_item`** ✅ – ošetřen `AttributeError` při regexu.
2. **Použít vlastní výjimku** místo `RuntimeError` v `_require_cfg` ✅ – zavedena `ConfigurationError`.
3. **Přidat `LIMIT`** do `label2entity` a `string2entity` ✅ – přidán parametr `limit` (výchozí 10) a `lang` u `label2entity`.
4. **Opravit porovnávání Quantity** v `update_unique_property` ✅ – srovnávací klíč nyní zohledňuje jednotku jen pro Quantity.
5. **Podpora `LOD_` prefixů** ✅ – `_cfg_value` nyní čte i `LOD_<NAME>` proměnné.
6. **Implementovat `ClaimBuilder`** ✅ – nový modul `lod/claim_builder.py` centralizuje tvorbu claimů a kvalifikátorů.
7. **Implementovat `DateNormalizer`** ✅ – nový modul `lod/date_normalizer.py` centralizuje normalizaci datumů; římské číslice jsou volitelné.
8. **Cachování `properties` a prefix blocku** ✅ – `list_properties()` je nyní cachováno s TTL 5 minut a `refresh_properties()` umožňuje invalidaci; PREFIX block je cachován pro každý project/host klíč.
9. **`WikibaseClient`** ✅ – nový modul `lod/wikibase_client.py` zapouzdřuje konfiguraci, lazy `site`/`repo`, cachované properties, prefix block a SPARQL/editační helpery. Globální mutable stav `site`/`repo`/`properties` v `lod/wikibase.py` byl nahrazen delegací na default klienta.

Zbývá: **Přidat type hints** do nejdůležitějších veřejných funkcí, případně implementovat hromadné editace (`BatchEditor`) nebo async SPARQL helpery.

---

## 9. Stav legacy funkcí

Následující funkce byly odstraněny a nyní vyhazují `DeprecationError` s návodem na náhradu:

- `add_qualifier`
- `add_qualifier_q`
- `add_qualifier_str`
- `add_qualifier_dat`
- `remove_claim_q`
- `remove_claim_str`
- `remove_claim_dat`
- `remove_qualifier_str`

Místo nich by se mělo používat:

```python
# Přidání claimu s kvalifikátorem
client.add_claim(item, data, property="P1", value="Q2", quals=[("P3", "Q4")])

# Odstranění claimu podle hodnoty
client.remove_claim(item, data, property="P1", value="Q2")

# Aplikace změn
item.editEntity(data, summary="...")
```

Pokud některá z těchto funkcí zůstane veřejně používaná v jiných projektech, doporučuji nejprve provést analýzu závislostí před jejich odstraněním.

---

## 10. Poznámky k konzistenci s `.clinerules`

- Návrh respektuje konvenci `LOD_CONFIG_MODULE` – `WikibaseClient` by měl přijímat konfiguraci jako parametr.
- Prefxy zůstávají odvozeny pouze z `WIKIBASE_PROJECT_CODE` + `WIKIBASE_HOST` (včetně `LOD_` env variant).
- Nové ikony nejsou relevantní pro tento návrh.
- Smoke testy by měly být doplněny po implementaci fází 1–3.
- Environment proměnné s prefixem `LOD_` jsou nyní podporovány v `lod/wikibase.py` (`_cfg_value`).

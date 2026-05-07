# Data product továbbfejlesztése

## Projekt Célja
Egy napelemes adatfeldolgozó (ETL) és fizikai szimulációs pipeline kiterjesztése egy "Day-Ahead" (másnapi) termelés-előrejelző Deep Learning modellel. A fókusz a valósághű paramétereken, az átlátható (vibe-kódolható) implementáción és a valószínűségi előrejelzésen van.

## Ezek voltak a tanár felé tett ígéreteim
(Egy korábbi projektem így alakítom át)

- Hozzáadni legalább egy modellbetanítást
- Átírnám a próbafeladatban meghatározott változókat: 
    - új inverter teljesítmény (alacsonyabb, így megjelenik a clipping, ami most 0)
    - másik konkrét napelem, más dőlésszög
    - más helyszín (koordináta)
    - más időintervallum (1 év helyett több)

---

## Tudnivalók

***(Innentől már a korábban említett változtatások konkrétumai szerepelnek!)***

* A paramétereket egyetlen `config.py` tartalmazza, az alábbiak szerint frissítendő!

* Az adatok tárolása lokális `solar_data.duckdb` adatbázisban 

* Egyszerűsített felépítés: az újonnan bekerülő ML betanítás **egy új Jupyter Notebookban** (`solar_ml_pipeline.ipynb`) kap helyet, 
**Separation of Concerns:**
1.A meglévő (vagy frissített) 1-es notebook (analysis.ipynb vagy hasonló): Ez végzi az ETL-t, letölti az adatokat az OpenMeteo-ról, lefuttatja a pvlib szimulációt az új degradációs paraméterekkel, majd a kiszámolt p_ac_net (és egyéb) értékeket elmenti a lokális solar_data.duckdb adatbázisba.
2. Az új 2-es notebook (solar_ml_pipeline.ipynb): A kettő közötti kapcsolatot maga a DuckDB adatbázis fogja jelenteni. Az ML notebook egyszerűen rácsatlakozik az adatbázisra, kiolvassa a már tiszta, előkészített adatokat (Target és Features), és kizárólag az ML betanítással, a gördülő predikcióval és a vizualizációval foglalkozik. Ez így rendkívül robusztus.

## Predikciós modell: TFT
Temporal Fusion Transformer (TFT): Valószínűségi előrejelzés miatt.

*Indoklás: Nemcsak pontbecslést, hanem ipari szintű bizonytalansági sávokat (probabilistic forecast) ad.*

- **Darts csomaggal**:
A gyors prototipizálás érdekében  használunk a megvalósításhoz.

* **Célváltozó (Target):** `p_ac_net` (a hálózatra betáplált, degradációval és egyéb veszteségekkel csökkentett végső AC teljesítmény).
* **Bemenetek (Covariates):** `ghi`, `temp_air`, `wind_speed` (mint másnapi időjárás-előrejelzés), valamint időbeli feature-ök (`hour`, `month`).

Mit fog csinálni a projektünk a 2025-ös (Teszt) éven?
Bár az egész 2025-ös évre lefuttatjuk a kiértékelést, a modell a háttérben úgynevezett gördülő (rolling) vagy visszatesztelt (backtested) másnapi előrejelzést végez.

**Így képzeld el a folyamatot:**

A modell "felébred" 2024. december 31. éjfélkor. Megnézi a 2025. január 1-i időjárásadatokat, és megjósolja január 1. termelését. Eltároljuk a hibát.

A modell "lép egyet előre", felébred január 1. éjfélkor. Megnézi a január 2-i időjárást, és megjósolja január 2. termelését. Eltároljuk a hibát.

Ezt megcsinálja 365-ször.

A végén kapunk egy RMSE és MAPE hibaértéket, ami azt jelenti: "Ez a TFT modell átlagosan ennyit tévedett, amikor minden nap megpróbálta megjósolni a holnapi termelést egy éven keresztül."

A notebook végén pedig kiválasztunk egy tetszőleges (random) hetet 2025-ből, és csak arra a hétre kirajzoljuk a grafikont, hogy vizuálisan is megmutassuk az eredményt a P50-es várható értékkel és a bizonytalansági sávokkal.

## Koordináta, helyszín
47.4728, 21.6145, indoklás: Debreceni Déli Gazdasági Övezet középpontja, *Valós ipari/gyári környezet szimulálása.*

## Inverter (INVERTER_PDC0 config.py-ban)
**3000 wattos** inverter a legköltséghatékonyabb választás, hiszen úgy képes jelentős energiaveszteség (clipping) nélkül lefedni a nyári csúcsokat, hogy közben elkerüli egy indokolatlanul túlméretezett és drágább berendezés felárát

## Napelem panel
Jinko Solar Tiger Neo N-type 54HL4R-B (430 W)
*Indoklás: Modern iparági sztenderd, N-típusú, alacsony degradációval.*

Vegyük a 430 W-os modellt (ez egy gyakori teljesítményosztály ebben a szériában).

10 panellel számolva ez 4300 W DC csúcsteljesítményt (P_NOMINAL_WP) jelent.

A 3000 W-os inverterrel az ILR (Inverter Loading Ratio) így 1.43 lesz. Ez már nagyon határozott, életszerű clippinget (teljesítményvágást) fog eredményezni a nyári csúcsokon, ami csodálatos tanítóadat lesz az ML modellnek!

**Degradáció:** 
- A Jinko Tiger Neo adatlapja szerint az első évben 1% a degradáció, majd évente 0.4%
- A célváltozót (p_ac_net) már ez alapján számoljuk ki. Az ML modell ezt a lassú csökkenést "látens módon" meg fogja tanulni!

# Időintervallum
3 év és a 2023-01-01 – 2025-12-31 időszak.

**Train (Tanító) halmaz:** 2023.01.01. – 2024.12.31. 
(2 teljes év a mintázatok és az évszakok megtanulására).

**Test (Teszt/Kiértékelő) halmaz:** 2025.01.01. – 2025.12.31.
(1 teljes év, amin a modell úgy megy végig, mintha minden nap a "holnapi" termelést jósolná meg, ezen mérjük a másnapi predikció pontosságát).

## Elvárt Kimenet / Demonstráció
A notebook végén a TFT modell egy 2025-ös teszt-időszakon bizonyítja be, hogy a bevitt meteorológiai paraméterek alapján (és a múltbeli termelés, a clipping, valamint a degradációs trendek megtanulásával) mekkora pontossággal képes a "holnapi" órás áramtermelést bizonytalansági sávokkal együtt megjósolni.

## Side info-k
- Ha később a modellt "élőben" is akarod tesztelni, az OpenMeteo Forecast API-jával behúzhatod a jövőbeli időjárás-előrejelzést
- A korábbi virtuális környezet használható, de a `darts` csomagot és függőségeit telepíteni kell

---

## Elvégzett változtatások

| Paraméter | Régi érték | Új érték |
|---|---|---|
| `LATITUDE / LONGITUDE` | Budapest (47.47, 19.06) | Debrecen (47.4728, 21.6145) |
| `ALTITUDE / LOCATION_NAME` | 109 m, Budapest Infopark | 121 m, Debrecen Déli Gazdasági Övezet |
| `P_NOMINAL_WP` | 400 W (Trina Solar) | 430 W (Jinko Tiger Neo N-type) |
| `PDC0_TOTAL_W` | 4000 W | 4300 W |
| `GAMMA_PDC` | −0.0034 /°C | −0.0030 /°C (N-típus) |
| `ETA_M` | 0.208 | 0.2202 (~22%) |
| `U_C` | 26.744 | 28.77 (NOCT=41°C alapján újraszámítva) |
| `SURFACE_TILT` | 18° | 30° |
| `INVERTER_PDC0` | 5000 W | 3000 W |
| `ILR` | 0.80 | 1.433 (clipping!) |
| `START_DATE / END_DATE` | 2023-01-01 / 2023-12-31 | 2023-01-01 / 2025-12-31 |
| Új: `DEGRADATION_YEAR1 / ANNUAL` | – | 1% / 0,4% |
| Új: `SIMULATION_BASE_YEAR` | – | 2023 |
| Új: `TRAIN_START/END, TEST_START/END` | – | 2023–2024 / 2025 |
| Új: `TFT_INPUT/OUTPUT_LENGTH` | – | 168 / 24 |
| Új: `solar_ml_pipeline.ipynb` | – | Teljes TFT ML pipeline notebook |

---

## Ami még nincs kész (törlendő, ha elkészül)

- [x] **`data_loader.py` multi-év támogatás** – `ALL_YEARS`, `expected_rows()` hozzáadva; `load_weather_data()` évenként (2023–2025) fut, szökőév-tudatos ellenőrzéssel. `pv_calculator.py`: `_EXPECTED_TOTAL_ROWS`, `LOCATION_NAME`, deprecated `g_poa_effective→effective_irradiance` javítva. `analysis.ipynb`: 1.1 és 2.1 markdown cellák frissítve.

- [x] **`pv_calculator.py` – `p_ac_net` mentése DuckDB-be** – `_PV_DDL` séma bővítve (`p_ac_net`, `energy_loss_w`); `_write_pv_results` explicit 7 oszlopos INSERT; éves degradáció (`_degradation_factor`) per-timestamp vektorizálva `_enrich_with_system_losses`-ban; `run_pv_simulation` migrációs ALTER TABLE + truncate-on-force-reload; `get_pv_dataframe` olvassa a két új oszlopot. DuckDB: 26304 sor (2023–2025), 0 NULL p_ac_net-ben.

- [x] **`analysis.ipynb` – újrafuttatás elvégezve** – `run_pv_simulation(force_reload=True)` hívásra állítva; `data_loader.py` + `pv_calculator.py` CLI-ből futtatva: weather_data 26304 sor (2023–2025, szökőév-tudatos), pv_results 26304 sor, p_ac_net DuckDB-be mentve degradációval (2023: 5247 kWh, 2024: 5496 kWh, 2025: 5307 kWh).

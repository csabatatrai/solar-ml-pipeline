"""
config.py
=========
A solar-etl-simulation projekt egyetlen konfigurációs forrása.

Minden konstans itt van definiálva: helyszín, API paraméterek, panel adatok,
inverter adatok és adatbázis elérési út. A többi modul innen importál.
"""

# =============================================================================
# Helyszín: Debrecen, Déli Gazdasági Övezet
# Valós ipari/gyári környezet szimulálása
# =============================================================================
LATITUDE  = 47.4728   # °É  – Debrecen, Déli Gazdasági Övezet (WGS84)
LONGITUDE = 21.6145   # °K  – Debrecen, Déli Gazdasági Övezet (WGS84)
ALTITUDE      = 121       # m (tengerszint feletti magasság, Debrecen)
TIMEZONE      = "Europe/Budapest"
LOCATION_NAME = "Debrecen, Déli Gazdasági Övezet"

# =============================================================================
# OpenMeteo Historical Weather API
# Dokumentáció: https://open-meteo.com/en/docs/historical-weather-api
# =============================================================================
API_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
YEAR         = 2023        # backward-compat data_loader.py-hoz (évenként tölt le)
START_DATE   = "2023-01-01"   # teljes ETL időszak kezdete
END_DATE     = "2025-12-31"   # teljes ETL időszak vége

# Az OpenMeteo API által elvárt változónevek (raw request paraméterek)
HOURLY_VARS = [
    "shortwave_radiation",        # GHI  [W/m²] - globális vízszintes sugárzás
    "direct_normal_irradiance",   # DNI  [W/m²] - közvetlen normál sugárzás
    "diffuse_radiation",          # DHI  [W/m²] - szórt vízszintes sugárzás
    "temperature_2m",             # T_air [°C]  - levegő hőmérséklet 2 m-en
    "windspeed_10m",              # WS   [m/s]  - szélsebesség 10 m-en
]

# API mezőnevek → belső mezőnevek leképezése
API_COLUMN_MAP = {
    "shortwave_radiation":      "ghi",
    "direct_normal_irradiance": "dni",
    "diffuse_radiation":        "dhi",
    "temperature_2m":           "temp_air",
    "windspeed_10m":            "wind_speed",
}

# =============================================================================
# Adatbázis
# =============================================================================
DB_FILENAME = "solar_data.duckdb"
DB_PATH     = "data/" + DB_FILENAME  # DuckDB fájlútvonal (projekt gyökeréhez képest)

# =============================================================================
# Napelempark - Panel paraméterek
# Forrás: Jinko Solar Tiger Neo N-type 54HL4R-B (430 W)
# N-típusú monokrisztallinos, alacsony degradáció, magas hatásfok
# STC feltételek: 1000 W/m², 25 °C cellaholmérséklet, AM 1.5
# =============================================================================
N_PANELS     = 10
P_NOMINAL_WP = 430.0                    # Wp / panel (STC)
PDC0_TOTAL_W = N_PANELS * P_NOMINAL_WP  # 4300 W összes DC névleges teljesítmény

# Teljesítmény hőmérsékleti együttható: -0,30 %/K (N-típus, adatlap) → pvlib egységben
GAMMA_PDC = -0.0030   # 1/°C

# Modul hatásfok (STC): ~22,02 % (adatlap, Jinko Tiger Neo 430W)
# A pvlib.temperature.pvsyst_cell energiamérleg-számításához szükséges.
ETA_M = 0.2202

# PVsyst cellahőmérséklet modell paraméterei (lapostetős, ballasztos tartószerkezet)
# Jinko Tiger Neo NOCT = 41°C
# U_C = poa*(1 - eta_m/alpha)/(T_noct - T_air) = 800*(1-0.2202/0.9)/(41-20) = 28.77
U_C              = 28.77  # W/m²/K  állandó hőveszteségi tényező
U_V              = 0.0    # Ws/m³/K szélfüggő hőveszteségi tag (lapostető, zárt aerodinamika)
ALPHA_ABSORPTION = 0.9    # [-] elnyelt sugárzás aránya (pvlib alapértelmezés)

TEMP_REF = 25.0           # °C  STC referencia cellaholmérséklet

# =============================================================================
# Napelempark - Mechanikai konfiguráció
# =============================================================================
SURFACE_TILT    = 30    # ° vízszintestől mért dőlésszög (optimalizált, ~47°É szélességre)
SURFACE_AZIMUTH = 180   # ° (180 = déli tájolás, északi félgömbön optimális)

# POA (Plane of Array) irradiancia dekompozíciós modell
# Választás: haydavies
# Indoklás: figyelembe veszi a circumsolar és horizont körüli fényerősödést,
# pontosabb az isotropic modelinél Budapest részben felhős kontinentális éghajlatán,
# a Perez modellnél egyszerűbb és az éves energiahozam szintjén 1-3%-os eltérés
# várható köztük, ami interjúfeladat-szinten nem indokolja a plusz komplexitást.
POA_MODEL = "haydavies"

# =============================================================================
# Inverter paraméterek (pvlib.inverter.pvwatts)
# 3 kW-os inverter: ILR = 4300/3000 = 1,43 → határozott nyári clipping
# =============================================================================
INVERTER_PDC0 = 3000.0   # W  DC bemeneti teljesítmény, amelynél az inverter
                          # leadja a maximális AC teljesítményt
ETA_INV_NOM   = 0.96     # [-] névleges inverter hatásfok (iparági tipikus érték)
ETA_INV_REF   = 0.9637   # [-] pvwatts referencia hatásfok (pvlib alapértelmezés)

# DC/AC arány (Inverter Loading Ratio): 4300 W / 3000 W = 1,43
# Életszerű clipping nyári csúcsokon → jó tanítóadat az ML modellnek.
ILR = PDC0_TOTAL_W / INVERTER_PDC0  # 1.433

# =============================================================================
# Vizualizációs paletta és matplotlib alapbeállítások
#
# Primitív szemantikai tokenek – csak ezeket kell szerkeszteni.
# Minden COLORS kulcs ezekből épül fel, így egy token megváltoztatása
# az összes szemantikailag kapcsolódó grafikonelemen egyszerre érvényesül.
# =============================================================================

# ==============================================================================
# --- 1. Színpaletta – Elegant Sunset ------------------------------------------
# ==============================================================================

_WHITE         = "#FFFFFF"    # Háttér (vászon / panel)
_GoldenPollen  = "#ffc857ff"  # Napenergia, GHI, cellahőmérséklet, nyári trend
_BurntPeach    = "#e9724cff"  # Inverter-veszteség, csökkenő félév, másodlagos
_IntenseCherry = "#c5283dff"  # Rendszerveszteség, hőveszteség, negatív
_NightBordeaux = "#481d24ff"  # Clipping-veszteség, strukturális (cím, keret, szöveg)
_BalticBlue    = "#255f85ff"  # AC/DC termelés, pozitív energia

# ==============================================================================
# --- 2. Grafikon Specifikus Szótárak (Dictionary Mappings) --------------------
# ==============================================================================

# -- Alap: struktúra, szöveg, annotáció (minden grafikonon közös) -------------
C_BASE = {
    "bg":         _WHITE,           # fehér vászon háttér
    "bg_light":   _WHITE,           # panel / doboz háttér
    "neutral":    _NightBordeaux,   # referenciavonal (alpha a plotban)
    "neutral_dk": _NightBordeaux,   # keret, sötét semleges
    "title":      _NightBordeaux,   # főcím
    "text_dk":    _NightBordeaux,   # hangsúlyos szöveg
    "text_lt":    _BalticBlue,      # másodlagos szöveg
    "ann_fill":   _GoldenPollen,    # annotáció doboz háttér (alpha a plotban)
    "ann_edge":   _IntenseCherry,   # annotáció keret
}

# ── 1. Időjárási bemenetek ────────────────────────────────────────────────────
C_WEATHER = {
    "ghi":  _GoldenPollen,   # GHI irradiancia – napsárga
    "temp": _IntenseCherry,  # levegőhőmérséklet – meleg piros
    "wind": _BalticBlue,     # szélsebesség – hűvös kék
}

# ── 2. DC modell-validáció ────────────────────────────────────────────────────
C_DC_VALID: dict = {}

# ── 3. Cellahőmérséklet & termodegradáció ─────────────────────────────────────
C_THERMO = {
    "ac":      _BalticBlue,    # AC termelés (referencia oszlop)
    "loss":    _IntenseCherry, # termodegradációs veszteség-sáv
    "temp":    _GoldenPollen,  # cellahőmérséklet vonal
    "stc_ref": _BurntPeach,   # STC 25 °C vízszintes szaggatott vonal
}

# ── 4. Havi hőtérkép ──────────────────────────────────────────────────────────
# "YlOrRd": GoldenPollen → BurntPeach → IntenseCherry progresszióhoz legjobban illeszkedő beépített colormap.
C_HEATMAP = {
    "cmap": "YlOrRd",
}

# ── 5. Napi AC termelés ───────────────────────────────────────────────────────
C_DAILY = {
    "ac":      _GoldenPollen,    # napi termelés oszlop + éves átlag
    "rising":  _BalticBlue,  # mozgóátlag emelkedő félév – nyári napsárga
    "falling": _IntenseCherry, # mozgóátlag csökkenő félév – téli piros
}

# ── 6. KPI kártyák & Loss Waterfall ──────────────────────────────────────────
C_WATERFALL = {
    "ac":      _BalticBlue,    # valós AC (pozitív sáv / KPI kártya)
    "rising":  _GoldenPollen,  # emelkedő félév-jelölő – nyári nap
    "falling": _BurntPeach,    # csökkenő félév-jelölő – alkonyati barack
    "loss":    _IntenseCherry, # rendszerveszteség (soiling, mismatch…)
    "inv":     _BurntPeach,    # inverter konverziós veszteség
    "clip":    _NightBordeaux, # clipping veszteség – sötét, kritikus
    "temp":    _GoldenPollen,  # termodegradációs veszteség – hőség
}

# ── 7. Veszteségelemzés & ML potenciál ────────────────────────────────────────
C_LOSS = {
    "ac":        _BalticBlue,    # AC termelés (referencia sáv)
    "ac_tint":   _BalticBlue,    # AC halvány tintje (KPI doboz bg, alpha a plotban)
    "dc":        _BalticBlue,    # DC teljesítmény
    "loss":      _IntenseCherry, # rendszerveszteség
    "inv":       _BurntPeach,    # inverter veszteség
    "clip":      _NightBordeaux, # clipping veszteség – sötét, kritikus
    "temp":      _GoldenPollen,  # termodegradáció – meleg arany
    "ac_actual": _BalticBlue,    # Tényleges AC oszlop a vízesés-diagramon
    "ghi":       _GoldenPollen,  # GHI irradiancia referencia – napsárga
    "recovery":  _BalticBlue,    # AI/IoT sraffozás: visszanyerhető energia
}

# -- Compat réteg: régi COLORS-hivatkozások fallback-je -----------------------
COLORS = {**C_BASE, **C_WEATHER, **C_THERMO, **C_DAILY, **C_WATERFALL, **C_LOSS}

MPL_DEFAULTS = {
    "figure.dpi":        130,
    "font.size":         11,
    "axes.spines.top":   False,
    "axes.spines.right": False,
}

# =============================================================================
# Rendszerveszteség / system loss
# =============================================================================
# Az NREL PVWatts standard alapján a maradék, fizikai és környezeti veszteségek
# multiplikatív hatást gyakorolnak a hálózatra adott AC teljesítményre.
DETAILED_SYSTEM_LOSSES = {
    "soiling":      0.02,    # koszolódás                        – NREL PVWatts v5: 2,0%
    "shading":      0.03,    # árnyékolás (horizont-takarás is)  – NREL PVWatts v5: 3,0% (volt: 0.01)
    "mismatch":     0.02,    # modul-eltérés                     – NREL PVWatts v5: 2,0%
    "wiring":       0.02,    # DC kábelezési veszteség           – NREL PVWatts v5: 2,0%
    "connections":  0.005,   # csatlakozási veszteség            – NREL PVWatts v5: 0,5% (új)
    "lid":          0.015,   # fény okozta degradáció (LID)      – NREL PVWatts v5: 1,5%
    "nameplate":    0.0,     # névleges/tényleges telj. eltérés  – adatlap: 0/+5W tolerancia, panel sosem teljesít névleges alá
    "availability": 0.03,    # rendelkezésre állás + karbantart. – NREL PVWatts v5: 3,0%
    # snow: 0.0, age: 0.0   – NREL PVWatts v5 alapértéken 0%; nem kerülnek derate-be
}

# =============================================================================
# Degradáció – Jinko Tiger Neo N-type adatlap alapján
# =============================================================================
DEGRADATION_YEAR1  = 0.010   # 1,0 % az első évben (LID + kezdeti degradáció)
DEGRADATION_ANNUAL = 0.004   # 0,4 % évente az első év után

# Kumulatív degradációs faktorok évenként (a p_ac-ra alkalmazandó szorzó):
#   2023: 1 - 0.010              = 0.99000
#   2024: 0.990 * (1 - 0.004)   = 0.98604
#   2025: 0.986 * (1 - 0.004)   = 0.98209
SIMULATION_BASE_YEAR = 2023   # az első üzemév (referencia az évszámláláshoz)

# =============================================================================
# ML betanítás / teszt időszak határok
# =============================================================================
TRAIN_START = "2023-01-01"   # tanító halmaz kezdete
TRAIN_END   = "2024-12-31"   # tanító halmaz vége (2 teljes év)
TEST_START  = "2025-01-01"   # teszt halmaz kezdete (gördülő day-ahead backtest)
TEST_END    = "2025-12-31"   # teszt halmaz vége

# TFT modell hiperparaméterek (config-ban tartva a könnyű hangolhatóságért)
TFT_INPUT_LENGTH  = 168   # encoder ablakméret: 7 nap × 24 óra
TFT_OUTPUT_LENGTH = 24    # predikciós horizont: 1 nap (day-ahead)

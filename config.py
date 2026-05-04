"""
config.py
=========
A solar-etl-simulation projekt egyetlen konfigurációs forrása.

Minden konstans itt van definiálva: helyszín, API paraméterek, panel adatok,
inverter adatok és adatbázis elérési út. A többi modul innen importál.
"""

# =============================================================================
# Helyszín: Budapest, Magyarország (interjú helyszíne)
# =============================================================================
LATITUDE  = 47.4700   # °É  – Budapest, Infopark E épület (WGS84)
LONGITUDE = 19.0600   # °K  – Budapest, Infopark E épület (WGS84)
ALTITUDE      = 109       # m (tengerszint feletti magasság, budapesti átlag)
TIMEZONE      = "Europe/Budapest"
LOCATION_NAME = "Budapest, Infopark E épület"

# =============================================================================
# OpenMeteo Historical Weather API
# Dokumentáció: https://open-meteo.com/en/docs/historical-weather-api
# =============================================================================
API_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
YEAR         = 2023
START_DATE   = f"{YEAR}-01-01"
END_DATE     = f"{YEAR}-12-31"

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
DB_PATH     = DB_FILENAME          # DuckDB fájlútvonal (SQLAlchemy URL helyett)

# =============================================================================
# Napelempark - Panel paraméterek
# Forrás: Trina Solar Vertex S DE09.08 adatlap, TSM-400 DE09.08 sor (STC értékek)
# https://static.trinasolar.com/sites/default/files/EU_Datasheet_VertexS_DE09.08_2021_A.pdf
# STC feltételek: 1000 W/m², 25 °C cellaholmérséklet, AM 1.5
# =============================================================================
N_PANELS     = 10
P_NOMINAL_WP = 400.0                    # Wp / panel (STC)
PDC0_TOTAL_W = N_PANELS * P_NOMINAL_WP  # 4000 W összes DC névleges teljesítmény

# Teljesítmény hőmérsékleti együttható: -0,34 %/K (adatlap) → pvlib egységben
GAMMA_PDC = -0.0034   # 1/°C

# Modul hatásfok (STC): 20,8 % (adatlap, TSM-400 sor, "Module Efficiency ηm")
# A pvlib.temperature.pvsyst_cell energiamérleg-számításához szükséges:
# a nem villamos energiává alakított sugárzás hőként marad a cellában.
ETA_M = 0.208

# PVsyst cellahőmérséklet modell paraméterei (lapostetős, ballasztos tartószerkezet)
# Referencia: pvlib.temperature.pvsyst_cell dokumentáció
U_C              = 26.744 # W/m²/K  állandó hőveszteségi tényező
                          # Adatlapból levezetett (NOCT=43°C, 800W/m², 20°C, 1m/s):
                          # U_C = poa*(1 - eta_m/alpha)/(T_noct - T_air) = 800*0.769/23 = 26.744
U_V              = 0.0    # Ws/m³/K szélfüggő hőveszteségi tag
                          # (0.0: Fizikai realitás. Lapostetőn, zárt aerodinamikai rendszernél 
                          # a szél hűtőhatása minimális a tetőn megrekedő hő miatt.)
ALPHA_ABSORPTION = 0.9    # [-] elnyelt sugárzás aránya (pvlib alapértelmezés)

TEMP_REF = 25.0           # °C  STC referencia cellaholmérséklet

# =============================================================================
# Napelempark - Mechanikai konfiguráció
# =============================================================================
SURFACE_TILT    = 18    # ° vízszintestől mért dőlésszög (feladatból)
SURFACE_AZIMUTH = 180   # ° (180 = déli tájolás, északi félgömbön optimális)
                        # Megjegyzés: a feladat nem adja meg a tájolást;
                        # déli tájolás feltételezve az optimális hozam érdekében.

# POA (Plane of Array) irradiancia dekompozíciós modell
# Választás: haydavies
# Indoklás: figyelembe veszi a circumsolar és horizont körüli fényerősödést,
# pontosabb az isotropic modelinél Budapest részben felhős kontinentális éghajlatán,
# a Perez modellnél egyszerűbb és az éves energiahozam szintjén 1-3%-os eltérés
# várható köztük, ami interjúfeladat-szinten nem indokolja a plusz komplexitást.
POA_MODEL = "haydavies"

# =============================================================================
# Inverter paraméterek (pvlib.inverter.pvwatts)
# Max AC teljesítmény: 5 kW (feladatból)
# =============================================================================
INVERTER_PDC0 = 5000.0   # W  DC bemeneti teljesítmény, amelynél az inverter
                          # leadja a maximális AC teljesítményt
ETA_INV_NOM   = 0.96     # [-] névleges inverter hatásfok (iparági tipikus érték)
ETA_INV_REF   = 0.9637   # [-] pvwatts referencia hatásfok (pvlib alapértelmezés)

# DC/AC arány (Inverter Loading Ratio): 4000 W / 5000 W = 0,80
# Megjegyzés: kissé alulterhelt inverter a feladat adottságai alapján;
# valós rendszereknél ez tipikusan 1,1-1,3 között van.
ILR = PDC0_TOTAL_W / INVERTER_PDC0  # 0.80

# =============================================================================
# Vizualizációs paletta és matplotlib alapbeállítások
#
# Primitív szemantikai tokenek – csak ezeket kell szerkeszteni.
# Minden COLORS kulcs ezekből épül fel, így egy token megváltoztatása
# az összes szemantikailag kapcsolódó grafikonelemen egyszerre érvényesül.
# =============================================================================

# ==============================================================================
# --- 1. Színpaletta (Adatvizualizációs best practice tónusok) -----------------
# Tiszta RGB helyett modern, képernyőbarát és kontrasztos árnyalatok.
# ==============================================================================

# -- Fő Adatsor-tokenek (Napelem / Energetika specifikus) --
_GREEN      = "#10B981"   # AC termelés / Pozitív (Smaragdzöld - élénk, de nem neon)
_RED        = "#DE0B0B"   # Veszteség / Hőmérséklet (Tompított, modern piros)
_BLUE       = "#3B82F6"   # Hűvös adatok / Szélsebesség (Tiszta, olvasható kék)
_MAGENTA    = "#4B00F9"   # GHI / Sugárzás (Lila tónus a pirostól való jobb elválásért)
_LIGHTBLUE  = "#7DD3FC"   # Visszanyerhető potenciál / Sraffozás (Világoskék)
_ORANGE     = "#F97316"   # Termikus degradáció (Élénk, de természetes narancs)
_AMBER      = "#F59E0B"   # Alternatív sugárzás (Mély borostyán)
_TEAL       = "#0D9488"   # Szélsebesség alternatíva (Kékeszöld hűvös kontraszt)

# -- Részletes konverziós lánc színek --
_BRAND      = "#E11D48"   # Brand / AC (Határozott, modern málna)
_BRAND_TINT = "#FFE4E6"   # Brand halvány mosás (Annotáció dobozok háttérszíne)
_BLUE_EL    = "#4F46E5"   # Elektromos/konverziós veszteség (Indigó)
_BLUE_DC    = "#0284C7"   # DC oldal (Mélyebb tengerkék)

# -- Extrém értékek (Hőtérképhez, scatter-skálákhoz) --
_YELLOW     = "#FACC15"   # Átmeneti, meleg zónák
_DARKRED    = "#991B1B"   # Extrém forró / Kritikus
_DARKBLUE   = "#1E3A8A"   # Fagyos / Extrém hideg
_CYAN       = "#06B6D4"   # Hűvös, de nem fagyos
_PURPLE     = "#6B21A8"   # Kiugróan ritka / Extrém anomáliák

# -- Szürke skála és UI (Modern 'Slate' tónusok a prémium megjelenésért) --
_GRAY_DK    = "#475569"   # Rendszerveszteség, sötét struktúra
_GRAY_MD    = "#94A3B8"   # Csökkenő félév, másodlagos szöveg
_GRAY_LT    = "#CBD5E1"   # Semleges referenciavonal, rácsvonalak
_GRAY_BG    = "#F8FAFC"   # Scatter háttér (Tisztább, fényesebb világosszürke)
_INK_DK     = "#334155"   # Keret, sötét semleges
_INK_TEXT   = "#0F172A"   # Hangsúlyos szöveg (Majdnem fekete, de lágyabb)
_WHITE      = "#FFFFFF"   # Panel / doboz háttér (Tiszta fehér)
_BLACK      = "#020617"   # Főcím, abszolút kontraszt

# ==============================================================================
# --- 2. Grafikon Specifikus Szótárak (Dictionary Mappings) --------------------
# ==============================================================================

# -- Alap: struktúra, szöveg, annotáció (minden grafikonon közös) -------------
C_BASE = {
    "bg":         _GRAY_BG,     # scatter háttér
    "bg_light":   _WHITE,       # panel / doboz háttér
    "neutral":    _GRAY_LT,     # referenciavonal
    "neutral_dk": _INK_DK,      # keret, sötét semleges
    "title":      _BLACK,       # főcím
    "text_dk":    _INK_TEXT,    # hangsúlyos szöveg
    "text_lt":    _GRAY_MD,     # másodlagos szöveg
    "ann_fill":   _BRAND_TINT,  # annotáció doboz háttér
    "ann_edge":   _GREEN,       # annotáció keret
}

# ── 1. Időjárási bemenetek ────────────────────────────────────────────────────
C_WEATHER = {
    "ghi":  _YELLOW,  # GHI irradiancia
    "temp": _RED,      # levegőhőmérséklet
    "wind": _BLUE,     # szélsebesség
}

# ── 2. DC modell-validáció ────────────────────────────────────────────────────
C_DC_VALID: dict = {}

# ── 3. Cellahőmérséklet & termodegradáció ─────────────────────────────────────
C_THERMO = {
    "ac":      _GREEN,   # AC termelés (referencia oszlop)
    "loss":    _RED, # termodegradációs veszteség-sáv
    "temp":    _YELLOW,    # cellahőmérséklet vonal
    "stc_ref": _RED,     # STC 25 °C vízszintes szaggatott vonal
}

# ── 4. Havi hőtérkép ──────────────────────────────────────────────────────────
# A "YlOrRd" jó választás teljesítményhez. Alternatíva lehet a "Spectral_r" hőmérséklethez.
C_HEATMAP = {
    "cmap": "YlOrRd",
}

# ── 5. Napi AC termelés ───────────────────────────────────────────────────────
C_DAILY = {
    "ac":      _BLUE,  # napi termelés oszlop + éves átlag
    "rising":  _GREEN,  # mozgóátlag emelkedő félév (= ac)
    "falling": _RED,    # mozgóátlag csökkenő félév
}

# ── 6. KPI kártyák & Loss Waterfall ──────────────────────────────────────────
C_WATERFALL = {
    "ac":      _GREEN,    # valós AC (pozitív sáv / KPI kártya)
    "rising":  _BRAND,    # emelkedő félév-jelölő
    "falling": _GRAY_MD,  # csökkenő félév-jelölő
    "loss":    _RED,      # rendszerveszteség (soiling, mismatch…)
    "inv":     _BLUE_EL,  # inverter konverziós veszteség
    "clip":    _BLUE_DC,  # clipping veszteség
    "temp":    _ORANGE,   # termodegradációs veszteség
}

# ── 7. Veszteségelemzés & ML potenciál ────────────────────────────────────────
C_LOSS = {
    "ac":       _GREEN,      # AC termelés (referencia sáv)
    "ac_tint":  _GREEN,      # AC halvány tintje (KPI doboz bg)
    "dc":       _BLUE,       # DC teljesítmény
    "loss":     _RED,        # rendszerveszteség
    "inv":      _BLUE_EL,    # inverter veszteség
    "clip":     _BLUE_DC,    # clipping veszteség
    "temp":      _ORANGE,    # termodegradáció
    "ac_actual": _GREEN,     # Tényleges AC oszlop a vízesés-diagramon
    "ghi":       _AMBER,      # GHI irradiancia referencia
    "recovery":  _YELLOW,     # AI/IoT sraffozás: modellel visszanyerhető energia
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

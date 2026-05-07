"""
data_loader.py
--------------
OpenMeteo historikus időjárási adat letöltő és DuckDB tároló komponens.

Letölti a 2023-as év irradiancia, hőmérséklet és szélerősség adatait
Budapest, Infopark koordinátáira, majd DuckDB adatbázisba tárolja a
weather_data táblában.

Futtatás (opcionális, önállóan is tesztelhető):
    python data_loader.py

Az analysis.ipynb orchestrátorból importálva:
    from data_loader import load_weather_data, get_weather_dataframe
"""

import logging
import time

import duckdb
import pandas as pd
import requests

from config import (
    LATITUDE,
    LONGITUDE,
    START_DATE,
    END_DATE,
    TIMEZONE,
    DB_PATH,
    API_BASE_URL as OPENMETEO_URL,
    API_COLUMN_MAP as VARIABLE_MAP,
)

# ---------------------------------------------------------------------------
# Multi-év logika (a config START_DATE / END_DATE alapján)
# ---------------------------------------------------------------------------

_START_YEAR = int(START_DATE[:4])   # 2023
_END_YEAR   = int(END_DATE[:4])     # 2025
ALL_YEARS   = list(range(_START_YEAR, _END_YEAR + 1))  # [2023, 2024, 2025]


def expected_rows(year: int) -> int:
    """Évi várt óránkénti sorok száma – szökőév-tudatos."""
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return (366 if leap else 365) * 24

MAX_RETRIES: int = 3
RETRY_DELAY_S: float = 5.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Séma
# ---------------------------------------------------------------------------

_WEATHER_DDL = """
    CREATE TABLE IF NOT EXISTS weather_data (
        timestamp  TIMESTAMPTZ PRIMARY KEY,
        ghi        DOUBLE,
        dni        DOUBLE,
        dhi        DOUBLE,
        temp_air   DOUBLE,
        wind_speed DOUBLE
    )
"""


def init_db(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """
    Megnyitja (vagy létrehozza) a DuckDB adatbázist és biztosítja a sémát.

    Returns
    -------
    duckdb.DuckDBPyConnection
        Nyitott írható kapcsolat (hívónak kell .close()).
    """
    con = duckdb.connect(db_path)
    con.execute(_WEATHER_DDL)
    log.info("DuckDB inicializálva: %s", db_path)
    return con


# ---------------------------------------------------------------------------
# OpenMeteo API hívás
# ---------------------------------------------------------------------------


def _fetch_openmeteo(
    latitude: float = LATITUDE,
    longitude: float = LONGITUDE,
    year: int = _START_YEAR,
    timezone: str = TIMEZONE,
) -> dict:
    """
    Letölti az adott év összes óránkénti időjárási adatát az OpenMeteo
    historikus API-ból. Újrapróbálkozik MAX_RETRIES-szor hálózati hiba esetén.

    Returns
    -------
    dict
        Nyers JSON válasz az API-tól.

    Raises
    ------
    requests.HTTPError
        Ha az API nem 200-as státuszkódot ad vissza.
    RuntimeError
        Ha MAX_RETRIES után sem sikerül a lekérés.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "hourly": ",".join(VARIABLE_MAP.keys()),
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info(
                "OpenMeteo API lekérés – %d. kísérlet (koordináták: %.4f, %.4f, év: %d)",
                attempt, latitude, longitude, year,
            )
            resp = requests.get(OPENMETEO_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            log.info(
                "API válasz megérkezett, rekordok száma: %s",
                len(data.get("hourly", {}).get("time", [])),
            )
            return data
        except requests.exceptions.HTTPError as exc:
            log.error("HTTP hiba: %s – válasz: %s", exc, resp.text[:300])
            raise
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            log.warning("Hálózati hiba (%d/%d): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)

    raise RuntimeError(
        f"Az OpenMeteo API {MAX_RETRIES} kísérlet után sem válaszolt."
    ) from last_exc


# ---------------------------------------------------------------------------
# DataFrame összeállítás és tisztítás
# ---------------------------------------------------------------------------


def _build_dataframe(raw: dict, timezone: str = TIMEZONE) -> pd.DataFrame:
    """
    A nyers JSON válaszból tisztított, timezone-aware pandas DataFrame-t készít.

    Elvégzett lépések:
    - Oszlopok átnevezése VARIABLE_MAP alapján
    - DatetimeIndex beállítása, timezone localize
    - Negatív sugárzási értékek nullára csípése
    - Szélsebesség negatív értékeinek nullára csípése
    - NaN ellenőrzés és naplózása

    Returns
    -------
    pd.DataFrame
        Indexe: timezone-aware DatetimeIndex (Europe/Budapest),
        oszlopai: ghi, dni, dhi, temp_air, wind_speed
    """
    hourly = raw.get("hourly", {})
    if not hourly:
        raise ValueError("Az API válasz nem tartalmaz 'hourly' adatot.")

    df = pd.DataFrame(hourly).rename(columns=VARIABLE_MAP)
    df["timestamp"] = pd.to_datetime(df["time"])
    df = df.drop(columns=["time"]).set_index("timestamp")

    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(timezone)

    for col in ("ghi", "dni", "dhi"):
        if col in df.columns:
            df[col] = df[col].clip(lower=0.0)
    if "wind_speed" in df.columns:
        df["wind_speed"] = df["wind_speed"].clip(lower=0.0)

    nan_counts = df.isna().sum()
    if nan_counts.any():
        log.warning("NaN értékek az adatban:\n%s", nan_counts[nan_counts > 0])
    else:
        log.info("Nincs NaN érték – adatminőség rendben.")

    actual_year    = df.index[0].year
    exp_rows       = expected_rows(actual_year)
    if len(df) != exp_rows:
        log.warning(
            "Várt sorok: %d, kapott sorok: %d – hiányzó vagy dupla adatok lehetségesek.",
            exp_rows, len(df),
        )
    else:
        log.info("Sorok száma: %d (teljes %d. év, óránkénti) – OK", len(df), actual_year)

    return df[["ghi", "dni", "dhi", "temp_air", "wind_speed"]]


# ---------------------------------------------------------------------------
# DuckDB írás
# ---------------------------------------------------------------------------


def _write_to_db(df: pd.DataFrame, con: duckdb.DuckDBPyConnection) -> int:
    """
    A DataFrame sorait idempotens módon írja a weather_data táblába.

    DuckDB Replacement Scan: a lokális `weather_flat` változóra hivatkozik
    közvetlenül SQL-ből – nincs szükség explicit con.register() hívásra.

    Returns
    -------
    int
        Újonnan beírt sorok száma.
    """
    count_before = con.execute("SELECT COUNT(*) FROM weather_data").fetchone()[0]

    weather_flat = df.reset_index()[  # noqa: F841  (DuckDB replacement scan)
        ["timestamp", "ghi", "dni", "dhi", "temp_air", "wind_speed"]
    ]
    con.execute(
        "INSERT INTO weather_data SELECT * FROM weather_flat ON CONFLICT DO NOTHING"
    )

    inserted = con.execute("SELECT COUNT(*) FROM weather_data").fetchone()[0] - count_before
    if inserted:
        log.info("%d új sor beírva a weather_data táblába.", inserted)
    else:
        log.info("Nincs új adat – az adatbázis már naprakész.")
    return inserted


# ---------------------------------------------------------------------------
# Publikus API
# ---------------------------------------------------------------------------


def load_weather_data(
    db_path: str = DB_PATH,
    force_reload: bool = False,
) -> int:
    """
    Fő ETL belépési pont. Évenként tölti le a START_DATE–END_DATE időszakot és
    menti DuckDB-be. Idempotens: ha egy év adatai már megvannak és
    force_reload=False, az API-hívás elmarad.

    Returns
    -------
    int
        Összes újonnan beírt sorok száma.
    """
    total_inserted = 0

    with duckdb.connect(db_path) as con:
        con.execute(_WEATHER_DDL)

        for year in ALL_YEARS:
            exp = expected_rows(year)
            count = con.execute(
                "SELECT COUNT(*) FROM weather_data "
                "WHERE timestamp >= ? AND timestamp < ?",
                (f"{year}-01-01", f"{year + 1}-01-01"),
            ).fetchone()[0]

            if not force_reload and count >= exp:
                log.info(
                    "%d. év: már %d sor van – letöltés kihagyva "
                    "(force_reload=True-val kényszeríthető újra).",
                    year, count,
                )
                continue

            raw = _fetch_openmeteo(year=year)
            df  = _build_dataframe(raw)
            total_inserted += _write_to_db(df, con)

    return total_inserted


def get_weather_dataframe(db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Visszaadja a weather_data tábla teljes tartalmát timezone-aware
    DatetimeIndex-szel rendelkező pandas DataFrame-ként.

    A DuckDB TIMESTAMPTZ-t UTC-ként adja vissza; itt konvertáljuk
    Europe/Budapest zónába.

    Returns
    -------
    pd.DataFrame
        Index: DatetimeIndex (Europe/Budapest),
        Oszlopok: ghi, dni, dhi, temp_air, wind_speed
    """
    with duckdb.connect(db_path, read_only=True) as con:
        df = con.execute(
            "SELECT timestamp, ghi, dni, dhi, temp_air, wind_speed "
            "FROM weather_data ORDER BY timestamp"
        ).df()

    if df.empty:
        raise RuntimeError(
            "A weather_data tábla üres. Futtasd előbb a load_weather_data() függvényt."
        )

    df["timestamp"] = df["timestamp"].dt.tz_convert(TIMEZONE)
    df = df.set_index("timestamp")

    log.info(
        "weather_data betöltve: %d sor, %s – %s",
        len(df), df.index[0].isoformat(), df.index[-1].isoformat(),
    )
    return df


# ---------------------------------------------------------------------------
# Önálló futtatás (teszteléshez)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== data_loader.py önálló futtatás ===")
    n = load_weather_data()
    if n > 0:
        log.info("ETL kész: %d sor beírva.", n)
    df = get_weather_dataframe()
    print("\n--- Első 3 sor ---")
    print(df.head(3).to_string())
    print("\n--- Összefoglaló statisztika ---")
    print(df.describe().round(2).to_string())
    print(f"\nSorok száma: {len(df)}")
    print(f"Időszak: {df.index[0]} – {df.index[-1]}")

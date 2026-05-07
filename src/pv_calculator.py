"""
pv_calculator.py
----------------
PV teljesítményszámító komponens a solar-etl-simulation projekthez.

Beolvassa a weather_data táblát, lefuttatja a teljes pvlib pipeline-t,
és az eredményeket a pv_results táblába írja (DuckDB).

Kötelező pvlib függvények (feladat szerint):
  - pvlib.temperature.pvsyst_cell()
  - pvlib.pvsystem.pvwatts_dc()
  - pvlib.inverter.pvwatts()

Futtatás (opcionális, önállóan is tesztelhető):
    python pv_calculator.py

Az analysis.ipynb orchestrátorból importálva:
    from pv_calculator import run_pv_simulation, get_pv_dataframe
"""

import logging
import math

import duckdb
import pandas as pd
import pvlib

from config import (
    LATITUDE,
    LONGITUDE,
    ALTITUDE,
    TIMEZONE,
    LOCATION_NAME,
    DB_PATH,
    SURFACE_TILT,
    SURFACE_AZIMUTH,
    GAMMA_PDC,
    TEMP_REF,
    ETA_M,
    ALPHA_ABSORPTION,
    U_C,
    U_V,
    PDC0_TOTAL_W as PDC0_TOTAL,
    INVERTER_PDC0 as PDC0_INV,
    ETA_INV_NOM,
    ETA_INV_REF,
    POA_MODEL,
    DETAILED_SYSTEM_LOSSES,
    DEGRADATION_YEAR1,
    DEGRADATION_ANNUAL,
    SIMULATION_BASE_YEAR,
)
from data_loader import get_weather_dataframe, ALL_YEARS, expected_rows

_EXPECTED_TOTAL_ROWS = sum(expected_rows(y) for y in ALL_YEARS)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Séma
# ---------------------------------------------------------------------------

_PV_DDL = """
    CREATE TABLE IF NOT EXISTS pv_results (
        timestamp     TIMESTAMPTZ PRIMARY KEY,
        poa_global    DOUBLE,
        temp_cell     DOUBLE,
        p_dc          DOUBLE,
        p_ac          DOUBLE,
        p_ac_net      DOUBLE,
        energy_loss_w DOUBLE
    )
"""

_PV_MIGRATE = [
    "ALTER TABLE pv_results ADD COLUMN IF NOT EXISTS p_ac_net DOUBLE",
    "ALTER TABLE pv_results ADD COLUMN IF NOT EXISTS energy_loss_w DOUBLE",
]


# ---------------------------------------------------------------------------
# pvlib pipeline
# ---------------------------------------------------------------------------


def _compute_solar_position(df: pd.DataFrame) -> pd.DataFrame:
    """
    [1] Szolárpozíció számítás pvlib.location.Location segítségével.

    Returns
    -------
    pd.DataFrame
        solar_zenith, solar_azimuth oszlopokkal kiegészített DataFrame.
    """
    location = pvlib.location.Location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        tz=TIMEZONE,
        altitude=ALTITUDE,
        name=LOCATION_NAME,
    )
    solar_pos = location.get_solarposition(df.index)
    df = df.copy()
    df["solar_zenith"]  = solar_pos["zenith"]
    df["solar_azimuth"] = solar_pos["azimuth"]
    log.info("Szolárpozíció kiszámítva (%d időpont).", len(df))
    return df


def _compute_poa_irradiance(df: pd.DataFrame) -> pd.DataFrame:
    """
    [2] Síkbeli (POA) irradiancia számítás haydavies modellel.

    Returns
    -------
    pd.DataFrame
        poa_global [W/m²] oszloppal kiegészített DataFrame.
    """
    dni_extra = pvlib.irradiance.get_extra_radiation(df.index)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=SURFACE_TILT,
        surface_azimuth=SURFACE_AZIMUTH,
        solar_zenith=df["solar_zenith"],
        solar_azimuth=df["solar_azimuth"],
        dni=df["dni"],
        ghi=df["ghi"],
        dhi=df["dhi"],
        dni_extra=dni_extra,
        model=POA_MODEL,
    )
    df = df.copy()
    df["poa_global"] = poa["poa_global"].clip(lower=0.0)
    log.info(
        "POA irradiancia kiszámítva (haydavies). Max: %.1f W/m², éves összeg: %.0f kWh/m².",
        df["poa_global"].max(),
        df["poa_global"].sum() / 1000,
    )
    return df


def _compute_cell_temperature(df: pd.DataFrame) -> pd.DataFrame:
    """
    [3] Cellahőmérséklet számítás – KÖTELEZŐ függvény.

    pvlib.temperature.pvsyst_cell(
        poa_global, temp_air, wind_speed,
        u_c, u_v, eta_m, alpha_absorption
    )

    Returns
    -------
    pd.DataFrame
        temp_cell [°C] oszloppal kiegészített DataFrame.
    """
    df = df.copy()
    df["temp_cell"] = pvlib.temperature.pvsyst_cell(
        poa_global=df["poa_global"],
        temp_air=df["temp_air"],
        wind_speed=df["wind_speed"],
        u_c=U_C,
        u_v=U_V,
        module_efficiency=ETA_M,
        alpha_absorption=ALPHA_ABSORPTION,
    )
    log.info(
        "Cellahőmérséklet kiszámítva (pvsyst). Max: %.1f °C, átlag (nappali): %.1f °C.",
        df["temp_cell"].max(),
        df.loc[df["poa_global"] > 0, "temp_cell"].mean(),
    )
    return df


def _compute_dc_power(df: pd.DataFrame) -> pd.DataFrame:
    """
    [4] DC teljesítmény számítás – KÖTELEZŐ függvény.

    pvlib.pvsystem.pvwatts_dc(
        g_poa_effective, temp_cell,
        pdc0, gamma_pdc, temp_ref
    )

    Returns
    -------
    pd.DataFrame
        p_dc [W] oszloppal kiegészített DataFrame.
    """
    df = df.copy()
    df["p_dc"] = pvlib.pvsystem.pvwatts_dc(
        effective_irradiance=df["poa_global"],
        temp_cell=df["temp_cell"],
        pdc0=PDC0_TOTAL,
        gamma_pdc=GAMMA_PDC,
        temp_ref=TEMP_REF,
    )
    log.info(
        "DC teljesítmény kiszámítva (pvwatts_dc). Max: %.1f W, éves összeg: %.0f kWh.",
        df["p_dc"].max(),
        df["p_dc"].sum() / 1000,
    )
    return df


def _compute_ac_power(df: pd.DataFrame) -> pd.DataFrame:
    """
    [5] AC teljesítmény számítás – KÖTELEZŐ függvény.

    pvlib.inverter.pvwatts(pdc, pdc0, eta_inv_nom, eta_inv_ref)

    Negatív értékeket (éjszakai szivárgási veszteség modell) nullára vágjuk.

    Returns
    -------
    pd.DataFrame
        p_ac [W] oszloppal kiegészített DataFrame.
    """
    df = df.copy()
    p_ac_raw = pvlib.inverter.pvwatts(
        pdc=df["p_dc"],
        pdc0=PDC0_INV,
        eta_inv_nom=ETA_INV_NOM,
        eta_inv_ref=ETA_INV_REF,
    )
    df["p_ac"] = p_ac_raw.clip(lower=0.0)

    clipping_wh  = (df["p_dc"] - PDC0_INV).clip(lower=0.0).sum()
    annual_kwh   = df["p_ac"].sum() / 1000
    specific_yield   = annual_kwh / (PDC0_TOTAL / 1000)
    capacity_factor  = annual_kwh / (PDC0_TOTAL / 1000 * 8760) * 100

    log.info("AC teljesítmény kiszámítva (inverter.pvwatts).")
    log.info("  Éves AC termelés      : %.1f kWh", annual_kwh)
    log.info("  Fajlagos hozam        : %.1f kWh/kWp", specific_yield)
    log.info("  Kapacitásfaktor       : %.2f %%", capacity_factor)
    log.info("  Clipping veszteség    : %.1f Wh", clipping_wh)
    log.info(
        "  Csúcs AC teljesítmény : %.1f W @ %s",
        df["p_ac"].max(),
        df["p_ac"].idxmax().isoformat(),
    )
    return df


def _degradation_factor(year: int) -> float:
    """Kumulatív degradációs szorzó az adott évre (Jinko Tiger Neo adatlap)."""
    years_elapsed = max(0, year - SIMULATION_BASE_YEAR)
    return (1.0 - DEGRADATION_YEAR1) * ((1.0 - DEGRADATION_ANNUAL) ** years_elapsed)


def _enrich_with_system_losses(df: pd.DataFrame) -> pd.DataFrame:
    """Multiplikatív rendszer-veszteség + éves degradáció alkalmazása a pvlib AC kimenetre."""
    df = df.copy()
    derate_factor = math.prod(1.0 - loss for loss in DETAILED_SYSTEM_LOSSES.values())

    years = df.index.year
    deg_factors = pd.Series(
        [_degradation_factor(y) for y in years], index=df.index, dtype=float
    )
    total_factor = derate_factor * deg_factors

    df["p_ac_net"]      = df["p_ac"] * total_factor
    df["energy_loss_w"] = df["p_ac"] - df["p_ac_net"]

    for yr in sorted(years.unique()):
        f = _degradation_factor(yr)
        log.info(
            "  Degradációs faktor %d: %.5f (rendszerveszteséggel együtt: %.5f)",
            yr, f, derate_factor * f,
        )
    log.info(
        "Rendszer-veszteség + degradáció alkalmazva: alap derate = %.4f (%.2f%% veszteség)",
        derate_factor,
        (1.0 - derate_factor) * 100.0,
    )
    return df


# ---------------------------------------------------------------------------
# DuckDB írás
# ---------------------------------------------------------------------------


def _write_pv_results(
    df: pd.DataFrame,
    con: duckdb.DuckDBPyConnection,
    truncate_first: bool = False,
) -> int:
    """
    A pv_results DataFrame sorait idempotens módon írja az adatbázisba.

    DuckDB Replacement Scan: a lokális `pv_flat` változóra hivatkozik SQL-ből.

    Parameters
    ----------
    truncate_first : bool
        Ha True, a tábla tartalmát először törli (force_reload esetén).

    Returns
    -------
    int
        Beírt sorok száma.
    """
    if truncate_first:
        con.execute("DELETE FROM pv_results")
        log.info("pv_results tábla törölve (force_reload).")

    pv_flat = df[  # noqa: F841
        ["poa_global", "temp_cell", "p_dc", "p_ac", "p_ac_net", "energy_loss_w"]
    ].reset_index()

    con.execute("""
        INSERT INTO pv_results
            (timestamp, poa_global, temp_cell, p_dc, p_ac, p_ac_net, energy_loss_w)
        SELECT timestamp, poa_global, temp_cell, p_dc, p_ac, p_ac_net, energy_loss_w
        FROM pv_flat
        ON CONFLICT DO NOTHING
    """)

    inserted = con.execute("SELECT COUNT(*) FROM pv_results").fetchone()[0]
    if truncate_first or inserted:
        log.info("%d sor beírva a pv_results táblába.", inserted)
    else:
        log.info("Nincs új adat – a pv_results tábla már naprakész.")
    return inserted


# ---------------------------------------------------------------------------
# Publikus API
# ---------------------------------------------------------------------------


def run_pv_simulation(
    db_path: str = DB_PATH,
    force_reload: bool = False,
) -> pd.DataFrame:
    """
    Fő belépési pont. Lefuttatja a teljes pvlib pipeline-t és elmenti
    az eredményeket a pv_results táblába.

    Ha a tábla már tartalmaz 8760 sort és force_reload=False,
    kihagyja az újraszámítást (idempotens futtatás).

    Parameters
    ----------
    db_path : str
        DuckDB adatbázisfájl elérési útja.
    force_reload : bool
        Ha True, az újraszámítás megtörténik, ha az adatok már léteznek.

    Returns
    -------
    pd.DataFrame
        A teljes eredménytábla (poa_global, temp_cell, p_dc, p_ac),
        timezone-aware DatetimeIndex-szel.
    """
    # Init + migration + early-exit check.
    # The connection is always closed before any read_only open to avoid
    # DuckDB's "different configuration" conflict.
    with duckdb.connect(db_path) as con:
        con.execute(_PV_DDL)
        for stmt in _PV_MIGRATE:
            con.execute(stmt)
        count = con.execute("SELECT COUNT(*) FROM pv_results").fetchone()[0]
        filled = con.execute(
            "SELECT COUNT(*) FROM pv_results WHERE p_ac_net IS NOT NULL"
        ).fetchone()[0]

    needs_run = force_reload or count < _EXPECTED_TOTAL_ROWS or filled < _EXPECTED_TOTAL_ROWS

    if not needs_run:
        log.info(
            "A pv_results táblában már %d sor van (p_ac_net kitöltve: %d) – "
            "számítás kihagyva (force_reload=True-val kényszeríthető újra).",
            count,
            filled,
        )
        return get_pv_dataframe(db_path)

    log.info("PV szimuláció indítása...")
    df = get_weather_dataframe(db_path)
    df = _compute_solar_position(df)
    df = _compute_poa_irradiance(df)
    df = _compute_cell_temperature(df)
    df = _compute_dc_power(df)
    df = _compute_ac_power(df)
    df = _enrich_with_system_losses(df)

    with duckdb.connect(db_path) as con:
        _write_pv_results(df, con, truncate_first=force_reload)

    return df[["poa_global", "temp_cell", "p_dc", "p_ac", "p_ac_net", "energy_loss_w"]]


def get_pv_dataframe(db_path: str = DB_PATH) -> pd.DataFrame:
    """
    Visszaadja a pv_results tábla teljes tartalmát timezone-aware
    DatetimeIndex-szel rendelkező pandas DataFrame-ként.

    Az analysis.ipynb vizualizációs cellái ezt a függvényt importálják.

    Returns
    -------
    pd.DataFrame
        Index: DatetimeIndex (Europe/Budapest),
        Oszlopok: poa_global, temp_cell, p_dc, p_ac
    """
    with duckdb.connect(db_path, read_only=True) as con:
        df = con.execute(
            "SELECT timestamp, poa_global, temp_cell, p_dc, p_ac, p_ac_net, energy_loss_w "
            "FROM pv_results ORDER BY timestamp"
        ).df()

    if df.empty:
        raise RuntimeError(
            "A pv_results tábla üres. Futtasd előbb a run_pv_simulation() függvényt."
        )

    df["timestamp"] = df["timestamp"].dt.tz_convert(TIMEZONE)
    df = df.set_index("timestamp")

    if df["p_ac_net"].isna().any():
        df = _enrich_with_system_losses(df)

    log.info(
        "pv_results betöltve: %d sor, %s – %s",
        len(df), df.index[0].isoformat(), df.index[-1].isoformat(),
    )
    return df


# ---------------------------------------------------------------------------
# Önálló futtatás (teszteléshez)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== pv_calculator.py önálló futtatás ===")
    df = run_pv_simulation()
    print("\n--- Első 3 sor (nappali) ---")
    print(df[df["p_ac"] > 0].head(3).to_string())
    print("\n--- Összefoglaló statisztika ---")
    print(df.describe().round(2).to_string())
    annual_kwh = df["p_ac"].sum() / 1000
    print(f"\nÉves AC termelés: {annual_kwh:.1f} kWh")
    print(f"Fajlagos hozam  : {annual_kwh / (PDC0_TOTAL / 1000):.1f} kWh/kWp")

"""All settings in one place. Items marked VERIFY must be checked against your Oracle schema / FME."""
import os
from pathlib import Path

# --- folders (raw -> clean -> model-ready) ---
DATA_DIR = Path(os.getenv("PMIS_DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "01_raw"        # untouched copy of Oracle, one parquet per year
CLEAN_DIR = DATA_DIR / "02_clean"    # harmonized, quality-flagged, segment-aligned
MODEL_DIR = DATA_DIR / "03_model"    # long tables for modeling and Power BI
QC_DIR = DATA_DIR / "qc"             # lineage + quality reports

# --- Oracle (credentials from environment variables, never hard-coded) ---
ORACLE = {"user": os.getenv("PMIS_USER"), "password": os.getenv("PMIS_PASSWORD"),
          "dsn": os.getenv("PMIS_DSN")}          # e.g. "dbhost:1521/PMISPRD"
# Table name pattern. One table per year: {yy} = 2-digit year (PMIS16), {year} = 4-digit (PMIS_2016).
# Add the owner if needed: "OWNER.PMIS{yy}". One table with a PMISYR column: "OWNER.TABLENAME".
PMIS_TABLE = (os.getenv("PMIS_TABLE") or "").strip().strip("\"'").strip() or "PMIS{yy}"  # blank/quoted -> default


def table_for(year) -> str:
    year = int(year)          # accept 2025 or "2025"
    name = PMIS_TABLE.format(year=year, yy=f"{year % 100:02d}")
    bad = [f"{ch!r} (U+{ord(ch):04X})" for ch in name if not (ch.isascii() and (ch.isalnum() or ch in "_$#."))]
    if bad:   # hidden/odd characters (e.g. pasted from a web page) make Oracle reject the name
        raise ValueError(f"Table name {name!r} contains invalid characters: {bad}. "
                         f"Retype PMIS_TABLE by hand, e.g.  set PMIS_TABLE=PMIS{{yy}}")
    return name


def per_year_tables() -> bool:
    return "{year}" in PMIS_TABLE or "{yy}" in PMIS_TABLE
FETCH_SIZE = 20_000

# --- scope ---
YEARS = list(range(2016, 2026))
BASE_YEAR = 2025                     # segmentation + construction history everything aligns to
MIN_COVERAGE = 80                    # VERIFY with pavement team
DROP_FLAGS = {"X": "stale data (not re-measured)", "C": "construction during survey"}

# --- columns ---
CONTROL_COLS = ["ORIGKEY", "PMISYR", "ROUTE_ID", "FROM_MEASURE", "TO_MEASURE", "SYSTEM",
                "PAVTYP", "CONYR", "RESYR", "PRESYR", "CAPDAT", "COVERAGE", "PCI_2DEF",
                "COUNTY", "MDIST"]
DISTRESS_COLS = ["IRI", "RUT", "FAULTAV", "CRACK_RATIO", "STRUC_C_PCT"]
NUMERIC_CONTEXT = ["AADT", "TRUCKS"]                          # averaged across segments
STATIC_CONTEXT = ["PAVTHICK", "TACCDEPTH", "TPCCDEPTH", "BASEDPTH", "NHS", "FCLASS", "LANES"]
N_LAYERS = 8
LAYER_FIELDS = ["LAYR", "PROJECT", "PROJTYP", "SURTYP", "SURTHK", "BASTYP", "BASTHK",
                "SUBTYP", "SUBTHK", "RMVTYP", "RMVTHK"]
LAYER_COLS = [f"{f}{i}" for i in range(1, N_LAYERS + 1) for f in LAYER_FIELDS]  # VERIFY names

ALL_COLS = CONTROL_COLS + DISTRESS_COLS + NUMERIC_CONTEXT + STATIC_CONTEXT + LAYER_COLS

# --- DRAFT treatment thresholds: replace with the values found in the FME workspace ---
FUNC_MAX_IN = 2.0     # VERIFY: overlays thinner than this = functional
STR1_MAX_IN = 4.0     # VERIFY: between FUNC_MAX and this = structural level 1, above = level 2

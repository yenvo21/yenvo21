"""Step 1: copy PMIS from Oracle to local parquet, one file per year (the raw layer).
Re-runs read the parquet files instead of hitting Oracle again (use --force-extract to refresh)."""
from __future__ import annotations
import pandas as pd
import config as cfg


def connect():
    import oracledb                       # pip install oracledb (thin mode, no Oracle client needed)
    return oracledb.connect(**cfg.ORACLE)


def table_columns(con, table: str) -> list[str]:
    cur = con.cursor()
    cur.execute(f"SELECT * FROM {table} WHERE 1 = 0")
    return [d[0] for d in cur.description]


def extract_year(con, year: int) -> pd.DataFrame:
    per_year = cfg.per_year_tables()
    table = cfg.table_for(year)
    available = table_columns(con, table)
    cols = [c for c in cfg.ALL_COLS if c in available]
    missing = sorted(set(cfg.ALL_COLS) - set(available))
    if missing:
        print(f"  {year}: {len(missing)} columns not in {table} (kept as blank): {missing[:8]}...")

    sql = f"SELECT {', '.join(cols)} FROM {table}" + ("" if per_year else " WHERE PMISYR = :yr")
    cur = con.cursor()
    cur.arraysize = cfg.FETCH_SIZE
    cur.execute(sql, {} if per_year else {"yr": year})
    names = [d[0] for d in cur.description]
    chunks = []
    while rows := cur.fetchmany():
        chunks.append(pd.DataFrame(rows, columns=names))
    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=names)
    if per_year:
        df["PMISYR"] = year
    return df


def extract_all(force: bool = False, years=None) -> None:
    cfg.RAW_DIR.mkdir(parents=True, exist_ok=True)
    todo = [y for y in (years or cfg.YEARS) if force or not (cfg.RAW_DIR / f"pmis_{y}.parquet").exists()]
    if not todo:
        print("Raw layer up to date, skipping Oracle.")
        return
    with connect() as con:
        for y in todo:
            df = extract_year(con, y)
            df.to_parquet(cfg.RAW_DIR / f"pmis_{y}.parquet", index=False)
            print(f"  {y}: {len(df):,} rows")


def read_raw() -> pd.DataFrame:
    files = sorted(cfg.RAW_DIR.glob("pmis_*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

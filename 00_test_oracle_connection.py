"""
Iowa DOT PMIS -> longitudinal pavement panel (Oracle source)
==============================================================

Purpose
-------
Your PMIS data lives in Oracle as one table per year (e.g. PMIS16, PMIS17,
... PMIS25). This script queries each of those tables, tags each with its
survey year, and stitches them into one longitudinal panel keyed by a
STABLE segment identity that survives re-segmentation between years.

Why not just use ORIGKEY?
--------------------------
ORIGKEY is unique *within* a year but is derived from route + milepoints,
so it changes whenever a project causes a segment to be split or merged
(very common right after resurfacing/reconstruction). Joining years on
ORIGKEY directly will silently drop/duplicate segments.

Approach used here
-------------------
1. Within each year, keep the segment defined by (ROUTE_ID, FROM_MEASURE,
   TO_MEASURE).
2. To link year Y to year Y+1, match segments on ROUTE_ID where the
   milepoint ranges overlap by some minimum fraction (default 50%).
   This handles minor boundary drift and splits/merges reasonably well.
3. Each matched chain of segments across years gets one persistent
   SEGMENT_KEY (a synthetic UUID-like string), independent of ORIGKEY.

NOTE: Iowa DOT's LRS service exposes a "Management Sections" event table
(EFFECTIVE_START_DATE / EFFECTIVE_END_DATE / ORIG_KEY) that is the
authoritative way to do this instead of the overlap heuristic below --
see 02_fetch_lrs_layers.py. Once you've confirmed ORIG_KEY is stable
there, this matching step should be replaced with a lookup against that
table rather than the heuristic here.

Usage
-----
Explicit table list (full control over table/schema names):

    python 01_build_panel.py \
        --tables PMIS_SCHEMA.PMIS16,PMIS_SCHEMA.PMIS17,...,PMIS_SCHEMA.PMIS25 \
        --dsn hostname:port/service_name \
        --out panel.parquet

Auto-generated table list from a prefix + year range (assumes 2-digit-year
naming, i.e. PMIS16 for 2016 ... PMIS25 for 2025):

    python 01_build_panel.py \
        --table-prefix PMIS_SCHEMA.PMIS \
        --year-start 16 --year-end 25 \
        --dsn hostname:port/service_name \
        --out panel.parquet

Oracle credentials are read from environment variables -- NEVER pass them
on the command line or hardcode them. Set these before running:

    export ORACLE_USER=your_username
    export ORACLE_PASSWORD=your_password

(On Windows PowerShell: $env:ORACLE_USER = "..."; $env:ORACLE_PASSWORD = "...")

--dsn can also be set via the ORACLE_DSN environment variable instead of
the CLI flag, if you'd rather not put the host/service name in scripts or
shell history either.
"""

import argparse
import os
import uuid

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Columns we actually need downstream. Trim early -- PMIS exports have 200+
# columns and most (LAYR*, AGGSRC*, REMARKS*, etc.) aren't needed for cost
# projection. Add back any you need for your treatment-history logic.
# ---------------------------------------------------------------------------
KEEP_COLS = [
    "PMISYR", "ROUTE_ID", "FROM_MEASURE", "TO_MEASURE", "SYSTEM", "ROUTE",
    "DIR", "PMIS_LENGTH", "LANE_MILES", "MDIST", "COUNTY", "CITY",
    "PAVTYP", "DESCRIPT", "CONYR", "RESYR",
    "PCI_2", "IRI", "RUT", "CRACK_RATIO", "FAULT",
    "AADT", "TRUCKS", "NHS", "PCLASS", "FCLASS", "LANES",
    "SURFACE_TYPE", "TREATMENT",
    "PROJECT1", "PROJECT2", "PROJECT3", "PROJECT4",
    "PROJECT5", "PROJECT6", "PROJECT7", "PROJECT8",
    "PROJTYP1", "PROJTYP2", "PROJTYP3", "PROJTYP4",
    "PROJTYP5", "PROJTYP6", "PROJTYP7", "PROJTYP8",
]


def build_table_list(tables_arg: str | None, table_prefix: str | None,
                      year_start: int | None, year_end: int | None) -> list[str]:
    """
    Resolve the final list of Oracle table names to query, from either
    --tables (explicit, comma-separated) or --table-prefix + --year-start/
    --year-end (auto-generated as PREFIX + 2-digit year, e.g. PMIS16).
    """
    if tables_arg:
        return [t.strip() for t in tables_arg.split(",") if t.strip()]

    if table_prefix and year_start is not None and year_end is not None:
        return [f"{table_prefix}{yy:02d}" for yy in range(year_start, year_end + 1)]

    raise ValueError(
        "Provide either --tables (explicit comma-separated list) or "
        "--table-prefix together with --year-start and --year-end."
    )


def connect_oracle(dsn: str | None):
    """
    Open an Oracle connection using python-oracledb in 'thin' mode (no
    separate Oracle Instant Client install needed). Credentials come ONLY
    from environment variables -- never hardcode them or pass as CLI args,
    since CLI args are visible in shell history and process listings.
    """
    import oracledb  # imported here so the module has no hard dependency
                      # on oracledb unless this function is actually called

    user = os.environ.get("ORACLE_USER")
    password = os.environ.get("ORACLE_PASSWORD")
    if not user or not password:
        raise EnvironmentError(
            "ORACLE_USER and/or ORACLE_PASSWORD environment variables are "
            "not set. Set them before running, e.g.:\n"
            "  export ORACLE_USER=your_username\n"
            "  export ORACLE_PASSWORD=your_password"
        )
    dsn = dsn or os.environ.get("ORACLE_DSN")
    if not dsn:
        raise ValueError(
            "No DSN provided. Pass --dsn hostname:port/service_name or set "
            "the ORACLE_DSN environment variable."
        )

    print(f"Connecting to Oracle DSN {dsn} as {user} ...")
    return oracledb.connect(user=user, password=password, dsn=dsn)


def load_one_table(conn, table: str, expected_year: int | None = None) -> pd.DataFrame:
    """
    Query one yearly PMIS table for the columns we need. Validates that
    PMISYR is a single consistent value within the table (catches a table
    that unexpectedly holds mixed years, or a table/year mismatch).
    """
    col_list = ", ".join(KEEP_COLS)
    query = f"SELECT {col_list} FROM {table}"
    print(f"  Querying: {query[:120]}{'...' if len(query) > 120 else ''}")
    print(f"    (table = {table!r})")

    try:
        df = pd.read_sql(query, conn)
    except Exception as e:
        raise RuntimeError(
            f"Query failed for table {table!r}: {type(e).__name__}: {e}\n"
            f"  Common causes: table doesn't exist under this name/schema, "
            f"one of the KEEP_COLS column names doesn't exist in this "
            f"particular table (schemas can drift year to year -- check "
            f"with DESCRIBE {table}), or a stray character in the table "
            f"name (see repr above)."
        ) from e

    df.columns = [c.upper() for c in df.columns]  # normalize casing

    years_found = df["PMISYR"].dropna().unique()
    if len(years_found) != 1:
        raise ValueError(
            f"{table}: expected exactly one PMISYR value, found {years_found}. "
            f"Check whether this table holds mixed years."
        )
    if expected_year is not None and int(years_found[0]) != expected_year:
        print(f"  WARNING: {table} name implies year {expected_year} but "
              f"PMISYR column says {int(years_found[0])} -- using the "
              f"PMISYR column value as the source of truth.")

    print(f"  {table}: {len(df):,} rows, PMISYR={int(years_found[0])}")
    return df


def load_all_years_from_oracle(tables: list[str], dsn: str | None) -> pd.DataFrame:
    """
    Query each yearly PMIS table in turn and concatenate into one
    long-format DataFrame tagged by PMISYR.
    """
    conn = connect_oracle(dsn)
    try:
        frames = []
        for table in tables:
            # If the table name ends in 2 digits, use that as a sanity-check
            # expectation against the PMISYR column (best-effort, non-fatal).
            expected_year = None
            suffix = table[-2:]
            if suffix.isdigit():
                yy = int(suffix)
                expected_year = 2000 + yy if yy < 50 else 1900 + yy
            frames.append(load_one_table(conn, table, expected_year))
    finally:
        conn.close()

    all_years = pd.concat(frames, ignore_index=True)
    print(f"Pulled {len(tables)} tables, {len(all_years):,} segment-year rows, "
          f"years: {sorted(all_years['PMISYR'].unique())}")
    return all_years


def match_segments_across_years(all_years: pd.DataFrame,
                                 min_overlap_frac: float = 0.5) -> pd.DataFrame:
    """
    Assign a persistent SEGMENT_KEY that survives year-to-year resegmentation.

    Method: process years in order. For year 1, every segment gets a new key.
    For each subsequent year, try to match each segment to a segment from the
    immediately preceding year on the same ROUTE_ID whose milepoint range
    overlaps by >= min_overlap_frac of the shorter segment's length. If a
    match is found, inherit its SEGMENT_KEY; otherwise mint a new one
    (new construction, renumbered route, etc.).

    NOTE: this is O(segments_per_route^2) per year-pair, fine for a few
    thousand segments per year. If your network is much larger, spatially
    index by ROUTE_ID + county first (already done here) and consider an
    interval tree if it's still too slow.
    """
    all_years = all_years.sort_values(["PMISYR", "ROUTE_ID", "FROM_MEASURE"]).copy()
    all_years["SEGMENT_KEY"] = None
    years = sorted(all_years["PMISYR"].unique())

    prev_year_df = None
    for yr in years:
        cur = all_years[all_years["PMISYR"] == yr]
        if prev_year_df is None:
            all_years.loc[cur.index, "SEGMENT_KEY"] = [
                str(uuid.uuid4()) for _ in range(len(cur))
            ]
        else:
            keys = []
            for idx, row in cur.iterrows():
                candidates = prev_year_df[prev_year_df["ROUTE_ID"] == row["ROUTE_ID"]]
                match_key = None
                if len(candidates):
                    overlap_start = candidates["FROM_MEASURE"].clip(lower=row["FROM_MEASURE"])
                    overlap_end = candidates["TO_MEASURE"].clip(upper=row["TO_MEASURE"])
                    overlap_len = (overlap_end - overlap_start).clip(lower=0)
                    cur_len = row["TO_MEASURE"] - row["FROM_MEASURE"]
                    cand_len = candidates["TO_MEASURE"] - candidates["FROM_MEASURE"]
                    shorter_len = np.minimum(cur_len, cand_len).replace(0, np.nan)
                    overlap_frac = overlap_len / shorter_len
                    best = overlap_frac.idxmax() if overlap_frac.notna().any() else None
                    if best is not None and overlap_frac.loc[best] >= min_overlap_frac:
                        match_key = candidates.loc[best, "SEGMENT_KEY"]
                keys.append(match_key if match_key else str(uuid.uuid4()))
            all_years.loc[cur.index, "SEGMENT_KEY"] = keys
        prev_year_df = all_years.loc[cur.index]

    n_new = (all_years.groupby("SEGMENT_KEY")["PMISYR"].transform("count") == 1).sum()
    print(f"Assigned {all_years['SEGMENT_KEY'].nunique():,} persistent segment keys "
          f"across {len(years)} years ({n_new:,} appear in only one year).")
    return all_years


def add_derived_fields(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["LAST_TREATMENT_YR"] = panel["RESYR"].fillna(panel["CONYR"])
    panel["PAVEMENT_AGE"] = panel["PMISYR"] - panel["LAST_TREATMENT_YR"]

    # Detect a treatment event in THIS year: last-treatment year == PMISYR.
    panel["TREATED_THIS_YEAR"] = panel["LAST_TREATMENT_YR"] == panel["PMISYR"]

    # Year-over-year PCI change per segment (the actual deterioration rate
    # you'll fit curves to -- only meaningful once you have 2+ years loaded).
    panel = panel.sort_values(["SEGMENT_KEY", "PMISYR"])
    panel["PCI_PREV"] = panel.groupby("SEGMENT_KEY")["PCI_2"].shift(1)
    panel["YEAR_PREV"] = panel.groupby("SEGMENT_KEY")["PMISYR"].shift(1)
    panel["PCI_DELTA"] = panel["PCI_2"] - panel["PCI_PREV"]
    panel["YEARS_ELAPSED"] = panel["PMISYR"] - panel["YEAR_PREV"]
    panel["PCI_DELTA_PER_YR"] = panel["PCI_DELTA"] / panel["YEARS_ELAPSED"]

    return panel


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--tables",
                     help="Explicit comma-separated list of Oracle table "
                          "names, e.g. PMIS_SCHEMA.PMIS16,PMIS_SCHEMA.PMIS17,...")
    ap.add_argument("--table-prefix",
                     help="Alternative to --tables: prefix used with "
                          "--year-start/--year-end to auto-generate table "
                          "names as PREFIX + 2-digit year, e.g. "
                          "PMIS_SCHEMA.PMIS -> PMIS_SCHEMA.PMIS16")
    ap.add_argument("--year-start", type=int,
                     help="[with --table-prefix] first 2-digit year, e.g. 16")
    ap.add_argument("--year-end", type=int,
                     help="[with --table-prefix] last 2-digit year, e.g. 25")

    ap.add_argument("--dsn",
                     help="hostname:port/service_name. Can also be set via "
                          "ORACLE_DSN env var. Credentials always come from "
                          "ORACLE_USER / ORACLE_PASSWORD env vars, never "
                          "CLI args.")

    ap.add_argument("--out", default="pmis_panel.parquet")
    ap.add_argument("--min-overlap", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true",
                     help="Query each table one at a time and report "
                          "row counts / errors per table, WITHOUT "
                          "concatenating or writing output. Use this to "
                          "find which specific table(s) have a problem "
                          "before running the full pipeline.")
    args = ap.parse_args()

    tables = build_table_list(args.tables, args.table_prefix,
                               args.year_start, args.year_end)
    print(f"Resolved {len(tables)} tables to query: {tables}")

    if args.dry_run:
        conn = connect_oracle(args.dsn)
        results = []
        try:
            for table in tables:
                try:
                    df = load_one_table(conn, table)
                    results.append((table, "OK", f"{len(df):,} rows"))
                except Exception as e:
                    results.append((table, "FAILED", str(e).splitlines()[0]))
        finally:
            conn.close()
        print("\n--- Dry-run summary ---")
        for table, status, detail in results:
            print(f"  [{status}] {table}: {detail}")
        return

    all_years = load_all_years_from_oracle(tables=tables, dsn=args.dsn)
    matched = match_segments_across_years(all_years, args.min_overlap)
    panel = add_derived_fields(matched)

    panel.to_parquet(args.out, index=False)
    print(f"Wrote panel with {len(panel):,} rows to {args.out}")


if __name__ == "__main__":
    main()

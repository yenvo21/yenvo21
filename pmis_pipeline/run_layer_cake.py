"""
Build the layer cake from your PMIS snapshots and save it for review in Excel.

  python run_layer_cake.py --years 2024 2025 --routes 035   # small test first
  python run_layer_cake.py                                  # all years 2016-2025
  python run_layer_cake.py --trace <ORIGKEY>                # show one segment's cake
  python run_layer_cake.py --demo                           # no Oracle needed

Outputs (in PMIS_DATA_DIR/02_clean):
  layer_cake.parquet / .csv         one row per segment per construction event
  layer_cake_summary.parquet / .csv one row per segment (first/last work year, last project...)
  layer_cake_qc.xlsx                counts to check the result (open in Excel)
"""
import argparse
import pandas as pd
import config as cfg
import extract
import layer_cake as lc


def load_raw(args) -> pd.DataFrame:
    if args.demo:
        return lc.demo_raw()
    if args.years:
        cfg.YEARS = args.years
        if cfg.BASE_YEAR not in cfg.YEARS:
            cfg.BASE_YEAR = max(cfg.YEARS)
    extract.extract_all(force=args.force_extract, years=cfg.YEARS)
    raw = extract.read_raw()
    raw = raw[raw.PMISYR.isin(cfg.YEARS)]
    if args.routes:
        raw = raw[raw.ORIGKEY.astype(str).str.strip().str[:3].isin(args.routes)]
    return raw


def check_layer_columns(raw: pd.DataFrame) -> None:
    found = [c for c in cfg.LAYER_COLS if c in raw.columns and raw[c].notna().any()]
    print(f"Layer columns with data: {len(found)} of {len(cfg.LAYER_COLS)} expected")
    for f in cfg.LAYER_FIELDS:
        n = sum(1 for i in range(1, cfg.N_LAYERS + 1) if f"{f}{i}" in found)
        print(f"   {f:<8} {n}/{cfg.N_LAYERS}" + ("   <-- no data: column name wrong in config.py, or column empty" if n == 0 else ""))
    if not any(c.startswith("LAYR") for c in found):
        raise SystemExit("No LAYR columns found. Run check_columns.py and fix LAYER_FIELDS / LAYER_COLS in config.py.")


def qc_tables(cake: pd.DataFrame, summary: pd.DataFrame) -> dict:
    return {
        "events_per_segment": summary.N_EVENTS.value_counts().sort_index().rename("SEGMENTS").to_frame(),
        "project_source": cake.PROJECT_SOURCE.value_counts().to_frame("EVENTS"),
        "projtyp_source": cake.PROJTYP_SOURCE.value_counts().to_frame("EVENTS"),
        "projtyp_values": cake.PROJTYP.value_counts(dropna=False).to_frame("EVENTS"),
        "check_vs_conyr_resyr": summary.CHECK_VS_PMIS.value_counts().to_frame("SEGMENTS"),
        "last_work_year": summary.LAST_WORK_YR.value_counts().sort_index().to_frame("SEGMENTS"),
        "dropped_later": cake.DROPPED_LATER.value_counts().to_frame("EVENTS"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+")
    ap.add_argument("--routes", nargs="+")
    ap.add_argument("--trace")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--force-extract", action="store_true")
    args = ap.parse_args()

    raw = load_raw(args)
    print(f"Raw rows: {len(raw):,}  years: {sorted(int(y) for y in raw.PMISYR.unique())}")
    check_layer_columns(raw)

    cake, summary = lc.build_layer_cake(raw)
    print(f"Layer cake: {len(cake):,} events on {cake.SEG_ID.nunique():,} segments")

    if args.trace:
        pd.set_option("display.width", 250)
        print(cake[cake.SEG_ID == args.trace].to_string(index=False))
        print(summary[summary.SEG_ID == args.trace].T.to_string())
        return

    out = cfg.CLEAN_DIR
    out.mkdir(parents=True, exist_ok=True)
    cake.to_parquet(out / "layer_cake.parquet", index=False)
    summary.to_parquet(out / "layer_cake_summary.parquet", index=False)
    cake.to_csv(out / "layer_cake.csv", index=False)
    summary.to_csv(out / "layer_cake_summary.csv", index=False)
    qc = qc_tables(cake, summary)
    with pd.ExcelWriter(out / "layer_cake_qc.xlsx") as xw:
        for name, df in qc.items():
            df.to_excel(xw, sheet_name=name[:31])
    for name in ("project_source", "check_vs_conyr_resyr"):
        print(f"\n{name}:\n{qc[name].to_string()}")
    print(f"\nSaved to {out.resolve()}")


if __name__ == "__main__":
    main()

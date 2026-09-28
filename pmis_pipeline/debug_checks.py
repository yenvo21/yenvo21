"""
Phase 5-7: check every pipeline output and trace single segments.

  python debug_checks.py                      # run all checks -> PASS / WARN / FAIL
  python debug_checks.py --trace 0351100000...  # follow one segment from raw to model table
"""
import argparse
import pandas as pd
import config as cfg

# plausible value ranges per distress (VERIFY with pavement engineers)
RANGES = {"IRI": (20, 700), "RUT": (0, 2), "FAULTAV": (0, 1),
          "CRACK_RATIO": (0, 100), "STRUC_C_PCT": (0, 100)}
results = []


def check(name, ok, detail, warn_only=False):
    status = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    results.append(status)
    print(f"[{status}] {name}: {detail}")


def load():
    raw = pd.concat([pd.read_parquet(f) for f in sorted(cfg.RAW_DIR.glob("pmis_*.parquet"))])
    return (raw,
            pd.read_parquet(cfg.CLEAN_DIR / "segment_year_wide.parquet"),
            pd.read_parquet(cfg.CLEAN_DIR / "dropped_rows.parquet"),
            pd.read_parquet(cfg.MODEL_DIR / "dim_segment.parquet"),
            pd.read_parquet(cfg.MODEL_DIR / "fact_observed.parquet"))


def run_checks():
    raw, wide, dropped, dim, fact = load()
    print(f"\n=== RAW ({len(raw):,} rows) ===")
    years = sorted(raw.PMISYR.dropna().astype(int).unique())
    check("years present", set(cfg.YEARS) <= set(years), f"{years}")
    keylen = raw.ORIGKEY.astype(str).str.strip().str.len()
    check("ORIGKEY length = 19", (keylen == 19).mean() > 0.99, f"{(keylen == 19).mean():.1%} of rows")
    dup = raw.duplicated(["ORIGKEY", "PMISYR"]).sum()
    check("no duplicate ORIGKEY per year", dup == 0, f"{dup} duplicates")
    check("LRS columns filled", raw[["ROUTE_ID", "FROM_MEASURE", "TO_MEASURE"]].notna().all(axis=1).mean() > 0.95,
          f"{raw[['ROUTE_ID','FROM_MEASURE','TO_MEASURE']].notna().all(axis=1).mean():.1%} of rows")
    cap = pd.to_datetime(raw.CAPDAT, dayfirst=True, errors="coerce")
    check("CAPDAT parses as date", cap.notna().mean() > 0.9, f"{cap.notna().mean():.1%} parsed "
          f"(sample raw values: {raw.CAPDAT.dropna().astype(str).head(3).tolist()})", warn_only=True)

    print(f"\n=== QUALITY FILTER ===")
    pct = len(dropped) / len(raw)
    check("share of rows dropped", pct < 0.15, f"{pct:.1%} dropped", warn_only=True)
    print(dropped.groupby(["PMISYR", "DROP_REASON"]).size().unstack(fill_value=0).to_string())

    print(f"\n=== SEGMENT ALIGNMENT ({len(wide):,} segment-years) ===")
    low = (wide.PCT_COVERED < 90).mean()
    check("segments >= 90% covered", low < 0.10, f"{low:.1%} of segment-years below 90%", warn_only=True)
    per_year = wide.groupby("PMISYR").SEG_ID.nunique()
    check("segments per year stable", per_year.min() > 0.8 * per_year.max(),
          f"min {per_year.min():,} / max {per_year.max():,}", warn_only=True)

    print(f"\n=== TREATMENT ({len(dim):,} segments) ===")
    unk = (dim.TREATMENT == "UNKNOWN").mean()
    check("treatment assigned", unk < 0.10, f"{unk:.1%} UNKNOWN", warn_only=True)
    print(dim.TREATMENT.value_counts().to_string())

    print(f"\n=== FINAL FACT TABLE ({len(fact):,} rows) ===")
    check("no negative age", (fact.AGE < 0).sum() == 0, f"{(fact.AGE < 0).sum()} rows")
    check("age plausible (<= 60)", (fact.AGE > 60).mean() < 0.01, f"max age {fact.AGE.max()}", warn_only=True)
    for d, (lo, hi) in RANGES.items():
        v = fact.loc[fact.DISTRESS == d, "VALUE"]
        if len(v):
            bad = ((v < lo) | (v > hi)).mean()
            check(f"{d} in [{lo}, {hi}]", bad < 0.01, f"{bad:.2%} outside; median {v.median():.2f}",
                  warn_only=True)
    obs = fact.groupby(["SEG_ID", "DISTRESS"]).size()
    check("observations per segment", obs.median() >= 3, f"median {obs.median():.0f} per segment-distress",
          warn_only=True)

    print(f"\nSummary: {results.count('PASS')} PASS, {results.count('WARN')} WARN, {results.count('FAIL')} FAIL")


def trace(seg_id):
    raw, wide, dropped, dim, fact = load()
    pd.set_option("display.width", 220)
    r = dim[dim.SEG_ID == seg_id]
    if r.empty:
        raise SystemExit(f"{seg_id} not found in dim_segment (is it a {cfg.BASE_YEAR} ORIGKEY?)")
    route, a, b = r.iloc[0][["ROUTE_ID", "FROM_MEASURE", "TO_MEASURE"]]
    print(f"\n1) Segment: {seg_id}  route {route}  miles {a}-{b}")
    print(r.T.to_string())
    src = raw[(raw.ROUTE_ID == route) & (raw.TO_MEASURE > a) & (raw.FROM_MEASURE < b)]
    print("\n2) Raw rows overlapping it, every year:")
    print(src[["PMISYR", "ORIGKEY", "FROM_MEASURE", "TO_MEASURE", "CAPDAT", "PCI_2DEF"] + cfg.DISTRESS_COLS]
          .sort_values(["PMISYR", "FROM_MEASURE"]).to_string(index=False))
    print("\n3) Aligned (length-weighted) values:")
    print(wide[wide.SEG_ID == seg_id].sort_values("PMISYR").round(2).to_string(index=False))
    print("\n4) Final model rows:")
    print(fact[fact.SEG_ID == seg_id].sort_values(["DISTRESS", "MEAS_YR"])
          [["DISTRESS", "PMISYR", "MEAS_YR", "AGE", "VALUE", "TREATMENT"]].round(2).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace")
    a = ap.parse_args()
    trace(a.trace) if a.trace else run_checks()

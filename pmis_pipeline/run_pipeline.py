"""
PMIS pipeline:  Oracle -> raw parquet -> clean/align (wide) -> pivot (long) -> model tables + QC

  python run_pipeline.py                 # normal run (extracts only missing years)
  python run_pipeline.py --force-extract # re-pull every year from Oracle
  python run_pipeline.py --demo          # synthetic data, no Oracle needed
  python run_pipeline.py --years 2024 2025 --routes 035 080   # small debug run
"""
import argparse
import numpy as np
import pandas as pd
import config as cfg
import extract, transform, load
from lineage import Lineage


def make_demo_raw() -> None:
    """Fake snapshots: 1 route, re-segmented in 2021, resurfaced in 2020, one stale 'X' row."""
    rng = np.random.default_rng(1)
    cfg.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for yr in cfg.YEARS:
        cuts = [0, 5, 10] if yr < 2021 else [0, 3, 7, 10]
        rows = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            resyr = 2012 if yr < 2020 else 2020
            age = (yr - 1) - resyr
            r = dict(ORIGKEY=f"035" + "1" + "1" + f"{a:06d}{b:06d}" + "77", PMISYR=yr,
                     ROUTE_ID="R035", FROM_MEASURE=a, TO_MEASURE=b,
                     SYSTEM=np.nan if yr < 2018 else 1, PAVTYP="3", CONYR=1995, RESYR=resyr,
                     CAPDAT=f"15/06/{yr - 1}", COVERAGE=95,
                     PCI_2DEF="X" if (yr == 2019 and a == 0) else None,
                     IRI=60 + 5 * age + rng.normal(0, 3), RUT=0.05 + 0.02 * age,
                     FAULTAV=np.nan, CRACK_RATIO=max(0, 3 * age),
                     STRUC_C_PCT=np.nan if yr < 2017 else max(0, 1.5 * age),
                     AADT=8000, TRUCKS=1200, LAYR1=1995, PROJTYP1="O", SURTYP1="PCC", SURTHK1=10)
            if yr >= 2020:
                r.update(LAYR2=2020, PROJTYP2="S", SURTYP2="HMA", SURTHK2=3.0)
            rows.append(r)
        pd.DataFrame(rows).to_parquet(cfg.RAW_DIR / f"pmis_{yr}.parquet", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--force-extract", action="store_true")
    ap.add_argument("--years", type=int, nargs="+", help="only these years (debugging)")
    ap.add_argument("--routes", nargs="+", help="only ORIGKEYs starting with these route numbers, e.g. 035")
    args = ap.parse_args()

    print("1. Extract")
    if args.years:
        cfg.YEARS = args.years
        if cfg.BASE_YEAR not in cfg.YEARS:
            cfg.BASE_YEAR = max(cfg.YEARS)
    make_demo_raw() if args.demo else extract.extract_all(force=args.force_extract, years=cfg.YEARS)
    raw = extract.read_raw()
    raw = raw[raw["PMISYR"].isin(cfg.YEARS)]
    if args.routes:
        raw = raw[raw["ORIGKEY"].astype(str).str.strip().str[:3].isin(args.routes)]
        print(f"   debug subset: routes {args.routes} -> {len(raw):,} rows")

    print("2-7. Transform")
    lin = Lineage()
    lin.log("Read raw snapshots", len(raw), len(raw), f"PMIS {min(cfg.YEARS)}-{max(cfg.YEARS)} from Oracle")
    tables = transform.run(raw, lin)

    print("8. Load")
    load.write_parquet(tables)
    load.write_qc(raw, tables, lin.to_frame())
    print(f"Done. Outputs in {cfg.DATA_DIR.resolve()}")


if __name__ == "__main__":
    main()

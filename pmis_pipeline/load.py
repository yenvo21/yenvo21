"""Step 8: write outputs (parquet for Python/Power BI) and QC reports; optional write-back to Oracle."""
from __future__ import annotations
import pandas as pd
import config as cfg


def write_parquet(tables: dict[str, pd.DataFrame]) -> None:
    for d in (cfg.CLEAN_DIR, cfg.MODEL_DIR):
        d.mkdir(parents=True, exist_ok=True)
    tables["segment_year_wide"].to_parquet(cfg.CLEAN_DIR / "segment_year_wide.parquet", index=False)
    tables["dropped_rows"].to_parquet(cfg.CLEAN_DIR / "dropped_rows.parquet", index=False)
    for name in ("fact_observed", "dim_segment", "construction_layers"):
        tables[name].to_parquet(cfg.MODEL_DIR / f"{name}.parquet", index=False)


def write_qc(raw: pd.DataFrame, tables: dict, lineage: pd.DataFrame) -> None:
    cfg.QC_DIR.mkdir(parents=True, exist_ok=True)
    lineage.to_csv(cfg.QC_DIR / "lineage.csv", index=False)
    # where each distress series starts / has gaps
    comp = (raw.reindex(columns=["PMISYR"] + cfg.DISTRESS_COLS).groupby("PMISYR")[cfg.DISTRESS_COLS]
            .apply(lambda g: (g.notna().mean() * 100).round(1)))
    comp.to_csv(cfg.QC_DIR / "completeness_by_year.csv")
    # how many base-year ORIGKEYs existed each year (low = re-segmentation)
    base = set(raw.loc[raw.PMISYR == cfg.BASE_YEAR, "ORIGKEY"].astype(str).str.strip())
    pers = raw.groupby("PMISYR")["ORIGKEY"].apply(
        lambda s: round(100 * len(base & set(s.astype(str).str.strip())) / max(len(base), 1), 1))
    pers.rename("PCT_BASE_KEYS_PRESENT").to_csv(cfg.QC_DIR / "origkey_persistence.csv")
    tables["dropped_rows"].groupby(["PMISYR", "DROP_REASON"]).size().rename("ROWS") \
        .to_csv(cfg.QC_DIR / "dropped_by_reason.csv")
    tables["dim_segment"]["TREATMENT"].value_counts().to_csv(cfg.QC_DIR / "treatment_counts.csv")


def write_oracle(df: pd.DataFrame, table: str, con, batch: int = 50_000) -> None:
    """Optional: load a result into an existing Oracle table (truncate + insert) for Power BI."""
    cur = con.cursor()
    cur.execute(f"TRUNCATE TABLE {table}")
    cols = list(df.columns)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + str(i + 1) for i in range(len(cols)))})"
    data = df.astype(object).where(df.notna(), None).values.tolist()
    for i in range(0, len(data), batch):
        cur.executemany(sql, data[i:i + batch])
    con.commit()

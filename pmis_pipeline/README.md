# PMIS deterioration data pipeline

Turns yearly PMIS snapshots in Oracle into model-ready tables for Python modeling and Power BI.

```
Oracle PMIS ──► 01_raw (parquet per year) ──► 02_clean (wide, aligned) ──► 03_model (long) ──► models / Power BI
                  extract.py                    transform.py                   load.py
```

## Run
```bash
pip install -r requirements.txt
export PMIS_USER=... PMIS_PASSWORD=... PMIS_DSN="host:1521/service" PMIS_TABLE=PMIS
python run_pipeline.py            # add --force-extract to re-pull from Oracle, --demo to test without Oracle
```

## Steps (plain words)
| # | Step | What happens |
|---|------|--------------|
| 1 | Extract | Copy each PMIS year (2016–2025) from Oracle into its own file. Oracle is read once. |
| 2 | Harmonize | Same columns every year. SYSTEM (missing 2016–17) read from ORIGKEY. Survey year taken from CAPDAT. |
| 3 | Quality filter | Exclude carried-forward data (PCI_2DEF = X), construction during survey (C), low coverage. Excluded rows are kept in `dropped_rows` with a reason. |
| 4 | Align segments | Road segments get re-cut between years, so ORIGKEY changes. Every year is mapped onto the 2025 segments by route and mileposts (length-weighted). |
| 5 | Base attributes | Pavement type and construction history taken from the latest snapshot for all years. |
| 6 | Pivot layers | LAYR1–8, SURTYP1–8 … become one row per layer; used to derive the treatment. |
| 7 | Pivot distress | IRI, RUT, FAULTAV, CRACK_RATIO, STRUC_C_PCT columns become DISTRESS/VALUE rows. Age since treatment is added; surveys before the latest treatment are dropped. |
| 8 | Load | Parquet outputs + QC reports. Optional write-back to Oracle for Power BI. |

## Outputs
- `03_model/fact_observed.parquet` – one row per segment × distress × survey year (modeling input)
- `03_model/dim_segment.parquet` – one row per segment with treatment
- `03_model/construction_layers.parquet` – construction history, long format
- `qc/lineage.csv` – rows in/out per step (use directly in documentation)
- `qc/completeness_by_year.csv`, `qc/origkey_persistence.csv`, `qc/dropped_by_reason.csv`, `qc/treatment_counts.csv`

## To verify before production
Everything marked `VERIFY` in `config.py`: table name, layer column names, coverage threshold,
and the FUNC/STR1/STR2 thickness thresholds (draft values — take the real ones from the FME workspace).

"""Steps 2-7: clean, align segments across years, then PIVOT (wide -> long).
Order matters: clean and align while the data is still WIDE (one row per segment-year),
because alignment averages all distress columns of a segment at once. Unpivot last."""
from __future__ import annotations
import numpy as np
import pandas as pd
import config as cfg
from lineage import Lineage


# ---------- 2. harmonize ----------
def harmonize(raw: pd.DataFrame, lin: Lineage) -> pd.DataFrame:
    df = raw.reindex(columns=cfg.ALL_COLS).copy()      # same columns every year
    df["ORIGKEY"] = df["ORIGKEY"].astype(str).str.strip()
    for c in cfg.DISTRESS_COLS + cfg.NUMERIC_CONTEXT + ["FROM_MEASURE", "TO_MEASURE", "COVERAGE",
                                                       "CONYR", "RESYR", "PRESYR", "PMISYR"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # SYSTEM was not delivered 2016-2017; ORIGKEY = Route(3) System(1) Dir(1) BPost(6) EPost(6) County(2)
    df["SYSTEM"] = pd.to_numeric(df["SYSTEM"], errors="coerce").fillna(
        pd.to_numeric(df["ORIGKEY"].str[3], errors="coerce"))
    # PMISYR = publication year; CAPDAT = actual survey date
    cap = pd.to_datetime(df["CAPDAT"], dayfirst=True, errors="coerce")
    df["MEAS_YR"] = cap.dt.year.fillna(df["PMISYR"]).astype(int)
    lin.log("Harmonize columns", len(raw), len(df),
            "Same column list every year; SYSTEM recovered from ORIGKEY; survey year from CAPDAT")
    return df


# ---------- 3. quality flags ----------
def quality_filter(df: pd.DataFrame, lin: Lineage) -> pd.DataFrame:
    flag = df["PCI_2DEF"].fillna("").astype(str)
    reasons = [(flag.str.contains(k), v) for k, v in cfg.DROP_FLAGS.items()]
    reasons.append((df["COVERAGE"] < cfg.MIN_COVERAGE, f"coverage < {cfg.MIN_COVERAGE}%"))
    df["DROP_REASON"] = np.select([r[0] for r in reasons], [r[1] for r in reasons], default="")
    kept = df[df["DROP_REASON"] == ""]
    lin.log("Quality filter", len(df), len(kept),
            "Remove carried-forward (X) data, construction during survey (C), low coverage")
    return df          # keep all rows; DROP_REASON documents why rows are excluded later


# ---------- 4. align every year to the base-year segmentation (LRS overlap) ----------
def align_segments(df: pd.DataFrame, lin: Lineage) -> pd.DataFrame:
    base = df[df.PMISYR == cfg.BASE_YEAR][["ORIGKEY", "ROUTE_ID", "FROM_MEASURE", "TO_MEASURE"]]
    base = base.rename(columns={"ORIGKEY": "SEG_ID", "FROM_MEASURE": "B_FROM", "TO_MEASURE": "B_TO"})
    good = df[df.DROP_REASON == ""]
    m = base.merge(good, on="ROUTE_ID")
    m["W"] = (np.minimum(m.B_TO, m.TO_MEASURE) - np.maximum(m.B_FROM, m.FROM_MEASURE)).clip(lower=0)
    m = m[m.W > 0]

    num = cfg.DISTRESS_COLS + cfg.NUMERIC_CONTEXT
    for c in num:                                    # length-weighted average, ignoring blanks
        m[c + "_W"] = m[c] * m.W
        m[c + "_N"] = m.W.where(m[c].notna(), 0)
    g = m.groupby(["SEG_ID", "PMISYR", "MEAS_YR"])
    out = pd.DataFrame({c: g[c + "_W"].sum() / g[c + "_N"].sum().replace(0, np.nan) for c in num})
    out["PCT_COVERED"] = 100 * g.W.sum() / g.apply(lambda x: x.B_TO.iloc[0] - x.B_FROM.iloc[0],
                                                     include_groups=False)
    out["N_SOURCE_SEGMENTS"] = g.size()
    out = out.reset_index()
    lin.log("Align segments (LRS)", len(good), len(out),
            f"Map every year onto {cfg.BASE_YEAR} segments by route + mileposts, length-weighted")
    return out


# ---------- 5. static attributes + construction history from the BASE year ----------
def base_attributes(df: pd.DataFrame) -> pd.DataFrame:
    """Snapshot trap: older rows only know the construction history AS OF that year.
    Use the latest snapshot's history for every year."""
    keep = ["ORIGKEY", "ROUTE_ID", "FROM_MEASURE", "TO_MEASURE", "SYSTEM", "PAVTYP", "CONYR",
            "RESYR", "PRESYR", "COUNTY", "MDIST"] + cfg.STATIC_CONTEXT + cfg.LAYER_COLS
    return df[df.PMISYR == cfg.BASE_YEAR][keep].rename(columns={"ORIGKEY": "SEG_ID"})


# ---------- 6a. PIVOT #1: construction layers wide -> long ----------
def unpivot_layers(attrs: pd.DataFrame, lin: Lineage) -> pd.DataFrame:
    parts = []
    for i in range(1, cfg.N_LAYERS + 1):
        cols = {f"{f}{i}": f for f in cfg.LAYER_FIELDS}
        p = attrs[["SEG_ID"] + list(cols)].rename(columns=cols)
        parts.append(p.assign(LAYER_NO=i))
    layers = pd.concat(parts, ignore_index=True).dropna(subset=["LAYR"])
    layers["LAYR"] = pd.to_numeric(layers["LAYR"], errors="coerce")
    lin.log("Unpivot construction layers", len(attrs), len(layers),
            "LAYR1..8, SURTYP1..8 ... -> one row per segment per layer")
    return layers


# ---------- 6b. treatment (DRAFT rules - replace with the FME logic) ----------
def derive_treatment(attrs: pd.DataFrame, layers: pd.DataFrame) -> pd.DataFrame:
    last = layers.sort_values("LAYR").groupby("SEG_ID").tail(1)
    t = attrs[["SEG_ID", "PAVTYP", "CONYR", "RESYR"]].merge(last, on="SEG_ID", how="left")
    thk = pd.to_numeric(t.SURTHK, errors="coerce")
    base = np.where(t.PAVTYP.astype(str).str.startswith("3"), "COMP",
                    np.where(t.PAVTYP.astype(str) == "4", "FD", "OTHER"))
    level = np.where(thk < cfg.FUNC_MAX_IN, "FUNC", np.where(thk < cfg.STR1_MAX_IN, "STR1", "STR2"))
    t["TREATMENT"] = np.select(
        [t.PROJTYP.eq("O"), t.BASTYP.eq("CIP"),
         t.SURTYP.isin(["PCC", "PC7", "PC8"]) & t.PROJTYP.eq("S"),
         t.PROJTYP.eq("S") & thk.notna()],
        ["RECON", "CIR", "PCC_OVERLAY", pd.Series(level) + "_" + pd.Series(base)],
        default="UNKNOWN")
    t["TREATMENT_YR"] = t[["CONYR", "RESYR"]].max(axis=1)
    t["TREATMENT_RULE"] = "DRAFT - verify against FME"
    return t[["SEG_ID", "TREATMENT", "TREATMENT_YR", "TREATMENT_RULE"]]


# ---------- 7. PIVOT #2: distress wide -> long + age / clock reset ----------
def unpivot_distress(aligned: pd.DataFrame, attrs: pd.DataFrame, treat: pd.DataFrame,
                     lin: Lineage) -> pd.DataFrame:
    long = aligned.melt(id_vars=["SEG_ID", "PMISYR", "MEAS_YR", "PCT_COVERED"] + cfg.NUMERIC_CONTEXT,
                        value_vars=cfg.DISTRESS_COLS, var_name="DISTRESS", value_name="VALUE")
    n0 = len(long)
    long = long.dropna(subset=["VALUE"])
    lin.log("Unpivot distress", len(aligned), n0,
            "IRI, RUT, FAULTAV, CRACK_RATIO, STRUC_C_PCT columns -> DISTRESS + VALUE rows")
    lin.log("Drop blank distress values", n0, len(long),
            "e.g. FAULTAV on asphalt, STRUC_C_PCT before 2017")

    long = (long.merge(attrs[["SEG_ID", "SYSTEM", "PAVTYP", "COUNTY", "MDIST"] + cfg.STATIC_CONTEXT],
                       on="SEG_ID", how="left")
                .merge(treat, on="SEG_ID", how="left"))
    long["AGE"] = long["MEAS_YR"] - long["TREATMENT_YR"]
    n1 = len(long)
    long = long[long["AGE"] >= 0]
    lin.log("Keep current pavement life", n1, len(long),
            "Drop surveys taken before the latest treatment (clock reset)")
    return long


def run(raw: pd.DataFrame, lin: Lineage) -> dict[str, pd.DataFrame]:
    df = quality_filter(harmonize(raw, lin), lin)
    aligned = align_segments(df, lin)
    attrs = base_attributes(df)
    layers = unpivot_layers(attrs, lin)
    treat = derive_treatment(attrs, layers)
    obs = unpivot_distress(aligned, attrs, treat, lin)
    return {"segment_year_wide": aligned, "dim_segment": attrs.drop(columns=cfg.LAYER_COLS)
            .merge(treat, on="SEG_ID", how="left"), "construction_layers": layers,
            "fact_observed": obs, "dropped_rows": df[df.DROP_REASON != ""]}

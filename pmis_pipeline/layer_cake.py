"""
layer_cake.py  -  Python version of the engineer's FME step 1 ("map PMIS layer set").

What a "layer cake" is: every PMIS row carries up to 8 construction events (LAYR1..LAYR8).
Each event = the year work was done + what was placed (surface/base/subbase type and
thickness), what was removed (RMVTYP/RMVTHK), the PROJECT number and PROJTYP.
Stacked in year order they form the pavement's "cake" from original construction up.

This module:
  1. stack_layers        LAYR1..8 from EVERY snapshot -> one row per layer event
  2. map_to_base         attach events to the base-year segments (handles the 2016 realignment)
  3. consolidate         one row per segment per construction year; missing PROJECT/PROJTYP/
                         types are filled from other snapshots where the same event was complete
  4. fill_from_neighbors still-missing PROJECT/PROJTYP borrowed from contiguous segments
                         on the same route with the same construction year (projects span miles)
  5. summarize           per segment: original construction year, last work year, last project
                         type, and a check against the CONYR / RESYR columns
Every filled value records WHERE it came from (*_SOURCE columns) for the documentation.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import config as cfg

FILL_FIELDS = [f for f in cfg.LAYER_FIELDS if f != "LAYR"]


# 1 ---------------------------------------------------------------------------
def stack_layers(raw: pd.DataFrame) -> pd.DataFrame:
    keys = ["ORIGKEY", "PMISYR", "ROUTE_ID", "FROM_MEASURE", "TO_MEASURE"]
    parts = []
    for i in range(1, cfg.N_LAYERS + 1):
        cols = {f"{f}{i}": f for f in cfg.LAYER_FIELDS}
        p = raw.reindex(columns=keys + list(cols)).rename(columns=cols)
        parts.append(p.assign(LAYER_NO=i))
    L = pd.concat(parts, ignore_index=True)
    L["LAYR"] = pd.to_numeric(L["LAYR"], errors="coerce")
    L = L[L["LAYR"].between(1900, 2100)]            # blanks / zeros / typos out
    L = L[L["LAYR"] <= L["PMISYR"]]                 # work "done" after the snapshot = not real yet
    return L


# 2 ---------------------------------------------------------------------------
def base_segments(raw: pd.DataFrame) -> pd.DataFrame:
    b = raw[raw.PMISYR == cfg.BASE_YEAR][["ORIGKEY", "ROUTE_ID", "FROM_MEASURE", "TO_MEASURE",
                                          "CONYR", "RESYR"]]
    return b.rename(columns={"ORIGKEY": "SEG_ID", "FROM_MEASURE": "B_FROM", "TO_MEASURE": "B_TO"})


def map_to_base(L: pd.DataFrame, base: pd.DataFrame, min_share: float = 0.5) -> pd.DataFrame:
    """Keep an event for a base segment if its source piece covers >= min_share of it."""
    m = base[["SEG_ID", "ROUTE_ID", "B_FROM", "B_TO"]].merge(L, on="ROUTE_ID")
    ov = np.minimum(m.B_TO, m.TO_MEASURE) - np.maximum(m.B_FROM, m.FROM_MEASURE)
    m["SHARE"] = (ov / (m.B_TO - m.B_FROM)).clip(lower=0)
    return m[m.SHARE >= min_share]


# 3 ---------------------------------------------------------------------------
def consolidate(m: pd.DataFrame) -> pd.DataFrame:
    """One row per (segment, construction year). Latest snapshot wins; blanks are filled
    from older snapshots that recorded the same event."""
    m = m.sort_values(["SEG_ID", "LAYR", "PMISYR", "SHARE"], ascending=[True, True, False, False])
    g = m.groupby(["SEG_ID", "LAYR"])
    cake = g[FILL_FIELDS].first()                         # first NON-BLANK value, newest first
    latest = g[FILL_FIELDS].nth(0).set_index(cake.index)  # what the newest record alone says
    for f in ("PROJECT", "PROJTYP"):
        cake[f + "_SOURCE"] = np.where(latest[f].notna(), "latest snapshot",
                                       np.where(cake[f].notna(), "older snapshot", "missing"))
    cake["FIRST_SEEN"] = g.PMISYR.min()
    cake["LAST_SEEN"] = g.PMISYR.max()
    cake["N_SNAPSHOTS"] = g.PMISYR.nunique()
    cake = cake.reset_index()
    last_snap = m.groupby("SEG_ID").PMISYR.max().rename("SEG_LAST_SNAP")
    cake = cake.merge(last_snap, on="SEG_ID")
    # an event that vanished from later snapshots: data correction OR layer milled off
    cake["DROPPED_LATER"] = cake.LAST_SEEN < cake.SEG_LAST_SNAP
    return cake.drop(columns="SEG_LAST_SNAP")


# 4 ---------------------------------------------------------------------------
def fill_from_neighbors(cake: pd.DataFrame, base: pd.DataFrame, tol_mi: float = 0.05) -> pd.DataFrame:
    c = cake.merge(base[["SEG_ID", "ROUTE_ID", "B_FROM", "B_TO"]], on="SEG_ID")
    c = c.sort_values(["ROUTE_ID", "LAYR", "B_FROM"]).reset_index(drop=True)
    gap = c.B_FROM - c.groupby(["ROUTE_ID", "LAYR"]).B_TO.shift()
    c["RUN"] = (gap.isna() | (gap > tol_mi)).cumsum()      # contiguous stretch, same work year
    for f in ("PROJECT", "PROJTYP"):
        mode = c.groupby("RUN")[f].transform(
            lambda s: s.mode().iloc[0] if s.notna().any() else np.nan)
        fill = c[f].isna() & mode.notna()
        c.loc[fill, f] = mode[fill]
        c.loc[fill, f + "_SOURCE"] = "neighbor segment (same year, contiguous)"
    return c.drop(columns=["RUN"])


# 5 ---------------------------------------------------------------------------
def summarize(cake: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    c = cake.sort_values(["SEG_ID", "LAYR"])
    first = c.groupby("SEG_ID").head(1).set_index("SEG_ID")
    last = c.groupby("SEG_ID").tail(1).set_index("SEG_ID")
    s = pd.DataFrame({
        "N_EVENTS": c.groupby("SEG_ID").size(),
        "FIRST_WORK_YR": first.LAYR, "LAST_WORK_YR": last.LAYR,
        "LAST_PROJECT": last.PROJECT, "LAST_PROJTYP": last.PROJTYP,
        "LAST_PROJTYP_SOURCE": last.PROJTYP_SOURCE,
        "LAST_SURTYP": last.SURTYP, "LAST_SURTHK": last.SURTHK,
        "LAST_BASTYP": last.BASTYP, "LAST_RMVTYP": last.RMVTYP, "LAST_RMVTHK": last.RMVTHK,
    }).reset_index()
    s = s.merge(base[["SEG_ID", "CONYR", "RESYR"]], on="SEG_ID", how="right")
    pm_last = s[["CONYR", "RESYR"]].apply(pd.to_numeric, errors="coerce").max(axis=1)
    s["CHECK_VS_PMIS"] = np.select(
        [s.LAST_WORK_YR.isna(), s.LAST_WORK_YR == pm_last, s.LAST_WORK_YR > pm_last],
        ["no layer history", "agrees", "layer newer than CONYR/RESYR"],
        default="layer older than CONYR/RESYR")
    return s


def build_layer_cake(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = base_segments(raw)
    L = stack_layers(raw)
    cake = fill_from_neighbors(consolidate(map_to_base(L, base)), base)
    return cake, summarize(cake, base)


def demo_raw() -> pd.DataFrame:
    """Demo snapshots: route realigned in 2021; some project numbers/types missing."""
    rows = []
    for yr in range(2016, 2026):
        cuts = [0, 5, 10] if yr < 2021 else [0, 3, 7, 10]
        for a, b in zip(cuts[:-1], cuts[1:]):
            r = dict(ORIGKEY=f"R{yr}_{a}", PMISYR=yr, ROUTE_ID="R035", FROM_MEASURE=a, TO_MEASURE=b,
                     CONYR=1995, RESYR=2012 if yr < 2020 else 2020,
                     LAYR1=1995, PROJECT1="F-35-1", PROJTYP1="O", SURTYP1="PCC", SURTHK1=10,
                     LAYR2=2012, PROJECT2=None if yr >= 2021 else "IM-35-2",
                     PROJTYP2=None if yr >= 2019 else "S", SURTYP2="HMA", SURTHK2=3)
            if yr >= 2020:
                r.update(LAYR3=2020, PROJECT3="NHS-35-9" if a == 0 else None, PROJTYP3="S",
                         SURTYP3="HMA", SURTHK3=4, RMVTYP3="MILL", RMVTHK3=2)
            rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    cake, summary = build_layer_cake(demo_raw())
    pd.set_option("display.width", 220)
    print(cake.to_string(index=False))
    print(summary.to_string(index=False))

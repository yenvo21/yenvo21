"""
infer_family_rule.py  -  Recover the engineer's Family vs Individual Section rule from his results.

Idea: the rule left fingerprints. For every section we know (a) which composition he gave it
(export of his Power BI / Excel table) and (b) facts about its data (how many observations,
age span, how clean the trend is). A small decision tree finds the thresholds that best
separate "Individual Section" from "Family" -> e.g. "N_OBS >= 5 and TREND_R2 >= 0.6".
The tree is a HYPOTHESIS to confirm with the engineer, not the answer itself.

  python infer_family_rule.py engineer_models.csv
     engineer_models.csv : one row per ORIGKEY x DISTRESS (x TREATMENT...) with a
                           MODEL_COMPOSITION column, exported from his Power BI table
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text
import config as cfg

KEYS = ["ORIGKEY", "DISTRESS"]          # VERIFY: add TREATMENT/SYSTEM if his table has them per row


def section_features(fact: pd.DataFrame) -> pd.DataFrame:
    """Facts about each section's own data, computed from our fact_observed table."""
    f = fact.rename(columns={"SEG_ID": "ORIGKEY"}).sort_values(["ORIGKEY", "DISTRESS", "AGE"])

    def feats(g):
        x, y = g.AGE.to_numpy(float), g.VALUE.to_numpy(float)
        r2 = np.nan
        if len(g) >= 3 and np.ptp(x) > 0 and np.ptp(y) > 0:
            r2 = np.corrcoef(x, y)[0, 1] ** 2               # strength of the aging trend
        d = np.diff(y)
        return pd.Series({"N_OBS": len(g), "AGE_MIN": x.min(), "AGE_MAX": x.max(),
                          "AGE_SPAN": np.ptp(x), "TREND_R2": r2,
                          "SHARE_INCREASING": (d > 0).mean() if len(d) else np.nan,
                          "VALUE_RANGE": np.ptp(y)})

    return f.groupby(KEYS).apply(feats, include_groups=False).reset_index()


def infer(engineer: pd.DataFrame, feats: pd.DataFrame, max_depth: int = 3):
    d = engineer[KEYS + ["MODEL_COMPOSITION"]].merge(feats, on=KEYS, how="inner")
    print(f"Matched {len(d):,} of {len(engineer):,} engineer rows to our data\n")

    print("1) What separates the groups (median of each fact):")
    cols = ["N_OBS", "AGE_MIN", "AGE_MAX", "AGE_SPAN", "TREND_R2", "SHARE_INCREASING"]
    print(d.groupby("MODEL_COMPOSITION")[cols].median().round(2).to_string(), "\n")

    print("2) Share Individual by number of observations (a sharp jump = a count threshold):")
    ind = d.MODEL_COMPOSITION.str.contains("Individual", case=False)
    print(ind.groupby(d.N_OBS).mean().mul(100).round(0).rename("% Individual").to_string(), "\n")

    X = d[cols].fillna(-1)
    tree = DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=20, random_state=0)
    tree.fit(X, d.MODEL_COMPOSITION)
    acc = (tree.predict(X) == d.MODEL_COMPOSITION).mean()
    print(f"3) Candidate rule (reproduces {acc:.1%} of his assignments):")
    print(export_text(tree, feature_names=cols, decimals=2))
    wrong = d[tree.predict(X) != d.MODEL_COMPOSITION]
    return wrong        # the exceptions: ask the engineer about a few of these


if __name__ == "__main__":
    fact = pd.read_parquet(cfg.MODEL_DIR / "fact_observed.parquet")
    if len(sys.argv) > 1:
        eng = pd.read_csv(sys.argv[1])
    else:  # demo: pretend his rule was "Individual if >= 5 observations and trend R2 >= 0.6"
        feats_demo = section_features(fact)
        rng = np.random.default_rng(0)
        eng = feats_demo[KEYS].copy()
        n = rng.integers(2, 10, len(eng)); r2 = rng.uniform(0, 1, len(eng))
        fact = None
        eng["MODEL_COMPOSITION"] = np.where((n >= 5) & (r2 >= 0.6), "Individual Section", "Family")
        feats_demo["N_OBS"], feats_demo["TREND_R2"] = n, r2
        wrong = infer(eng, feats_demo)
        sys.exit()
    wrong = infer(eng, section_features(fact))
    wrong.to_csv(cfg.QC_DIR / "family_rule_exceptions.csv", index=False)
    print(f"Exceptions saved to {cfg.QC_DIR / 'family_rule_exceptions.csv'}")

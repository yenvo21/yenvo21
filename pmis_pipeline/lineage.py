"""Records rows in/out of every step -> becomes the data-lineage table in the documentation."""
import pandas as pd


class Lineage:
    def __init__(self):
        self.rows = []

    def log(self, step: str, rows_in: int, rows_out: int, rule: str):
        self.rows.append({"STEP": len(self.rows) + 1, "NAME": step, "ROWS_IN": rows_in,
                          "ROWS_OUT": rows_out, "RULE_IN_PLAIN_WORDS": rule})
        print(f"[{len(self.rows):02d}] {step:<32} {rows_in:>9,} -> {rows_out:>9,}")

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)

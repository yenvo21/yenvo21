"""Why does PMIS25 show only 1 column?  Run: python check_columns.py 2025"""
import sys
import oracledb
import config as cfg

year = int(sys.argv[1]) if len(sys.argv) > 1 else max(cfg.YEARS)
table = cfg.table_for(year)
name = table.split(".")[-1].upper()
cur = oracledb.connect(**cfg.ORACLE).cursor()

print(f"Table used by the pipeline: {table!r}\n")

cur.execute(f"SELECT COUNT(*) FROM {table}")
print(f"A) Rows:                              {cur.fetchone()[0]:,}")

cur.execute(f"SELECT * FROM {table} FETCH FIRST 1 ROWS ONLY")
cols = [d[0] for d in cur.description]
print(f"B) Columns when Python reads it:      {len(cols)}")
print(f"   first 15: {cols[:15]}")

cur.execute("SELECT COUNT(*) FROM user_tab_columns WHERE table_name = :n", n=name)
print(f"C) Columns in YOUR schema's {name}:   {cur.fetchone()[0]}")

cur.execute("""SELECT owner, COUNT(*) FROM all_tab_columns WHERE table_name = :n
               GROUP BY owner ORDER BY owner""", n=name)
print(f"D) Columns per owner (all schemas you can see):")
for owner, n in cur:
    print(f"     {owner}.{name}: {n}")

have = set(cols)
found = [c for c in cfg.ALL_COLS if c in have]
missing = [c for c in cfg.ALL_COLS if c not in have]
print(f"\nE) Expected by config.py: {len(cfg.ALL_COLS)} | found: {len(found)} | missing: {len(missing)}")
print(f"   missing (first 20): {missing[:20]}")

"""Phase 1: prove Python can reach Oracle and see the PMIS table. Run: python test_connection.py"""
import config as cfg

missing = [k for k, v in cfg.ORACLE.items() if not v]
if missing:
    raise SystemExit(f"Set these environment variables first: {['PMIS_' + m.upper() for m in missing]}")

import oracledb
print("python-oracledb", oracledb.__version__, "| DSN:", cfg.ORACLE["dsn"])
try:
    con = oracledb.connect(**cfg.ORACLE)
except oracledb.Error as e:
    print("CONNECTION FAILED:", e)
    print("  ORA-01017 -> wrong user/password | ORA-12514 -> wrong service name in DSN")
    print("  DPY-6005 / timeout -> host/port unreachable (VPN? firewall?)")
    print("  DPY-3010 / DPY-3015 -> database needs thick mode: install Oracle Instant Client and add")
    print("      oracledb.init_oracle_client(lib_dir=r'C:\\oracle\\instantclient_23_x') before connecting")
    raise SystemExit(1)

print("Connected. Database version:", con.version)
cur = con.cursor()
if cfg.per_year_tables():
    for y in cfg.YEARS:
        t = cfg.table_for(y)
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"  {t}: {cur.fetchone()[0]:,} rows")
        except oracledb.Error as e:
            print(f"  {t}: NOT FOUND ({e})")
else:
    cur.execute(f"SELECT PMISYR, COUNT(*) FROM {cfg.PMIS_TABLE} GROUP BY PMISYR ORDER BY PMISYR")
    for yr, n in cur.fetchall():
        print(f"  PMISYR {yr}: {n:,} rows")

# compare expected columns with what the table really has
t = cfg.table_for(max(cfg.YEARS))
cur.execute(f"SELECT * FROM {t} WHERE 1 = 0")
have = {d[0] for d in cur.description}
missing_cols = [c for c in cfg.ALL_COLS if c not in have]
print(f"\n{len(have)} columns in {t}; {len(missing_cols)} expected columns not found:")
print("  ", missing_cols)
print("  -> fix names in config.py (e.g. LAYR1 vs LAYR_1) before extracting.")
con.close()

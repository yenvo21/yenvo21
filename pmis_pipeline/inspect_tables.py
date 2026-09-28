"""Find out why a PMIS table shows only 1 column.  Run: python inspect_tables.py"""
import oracledb
import config as cfg

con = oracledb.connect(**cfg.ORACLE)
cur = con.cursor()
cur.execute("SELECT USER FROM dual")
print("Connected as:", cur.fetchone()[0])
print("PMIS_TABLE setting:", repr(cfg.PMIS_TABLE), "->", repr(cfg.table_for(max(cfg.YEARS))))

for yr in (min(cfg.YEARS), max(cfg.YEARS)):
    name = cfg.table_for(yr).split(".")[-1].upper()
    print(f"\n=== {name} ===")

    # 1. every object with this name, in every schema you can see
    cur.execute("""SELECT owner, object_type FROM all_objects
                   WHERE object_name = :n ORDER BY owner""", n=name)
    for owner, otype in cur:
        print(f"  object: {owner}.{name}  ({otype})")

    # 2. where synonyms point
    cur.execute("""SELECT owner, table_owner, table_name FROM all_synonyms
                   WHERE synonym_name = :n""", n=name)
    for owner, t_owner, t_name in cur:
        print(f"  synonym {owner}.{name} -> {t_owner}.{t_name}")

    # 3. how many columns each copy has
    cur.execute("""SELECT owner, COUNT(*) FROM all_tab_columns
                   WHERE table_name = :n GROUP BY owner ORDER BY owner""", n=name)
    for owner, n in cur:
        print(f"  {owner}.{name}: {n} columns")

    # 4. what the unqualified name actually resolves to
    t = cfg.table_for(yr)
    try:
        cur.execute(f"SELECT * FROM {t} WHERE 1 = 0")
    except oracledb.Error as e:
        print(f"  '{t}' could not be read: {e}")
        continue
    print(f"  '{t}' as the pipeline sees it: "
          + ", ".join(f"{d[0]} ({d[1].name if hasattr(d[1], 'name') else d[1]})" for d in cur.description[:10]))
con.close()

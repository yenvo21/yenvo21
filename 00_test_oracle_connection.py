"""
Oracle connection smoke test
==============================

Purpose: isolate "can I connect to Oracle at all" from the table-list /
--tables / --table-prefix logic in 01_build_panel.py. Run this FIRST.
If this works, any further error is about table names or column names,
not the connection itself.

Usage
-----
    python 00_test_oracle_connection.py --dsn hostname:port/service_name

Or set ORACLE_DSN as an environment variable and omit --dsn:

    python 00_test_oracle_connection.py

Credentials always come from ORACLE_USER / ORACLE_PASSWORD environment
variables (set these before running -- never pass them as CLI args):

    export ORACLE_USER=your_username
    export ORACLE_PASSWORD=your_password

Optional: pass --table to also try a trivial "SELECT COUNT(*)" against one
specific table, to confirm both the connection AND that a table name/grant
is correct, e.g.:

    python 00_test_oracle_connection.py --dsn host:port/service --table RAMS.PMIS16
"""

import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn",
                     help="hostname:port/service_name. Can also be set via "
                          "ORACLE_DSN env var.")
    ap.add_argument("--table",
                     help="Optional: run SELECT COUNT(*) against this table "
                          "after connecting, e.g. RAMS.PMIS16")
    args = ap.parse_args()

    print("Step 1: checking environment variables...")
    user = os.environ.get("ORACLE_USER")
    password = os.environ.get("ORACLE_PASSWORD")
    if not user:
        print("  FAILED: ORACLE_USER is not set.")
        sys.exit(1)
    if not password:
        print("  FAILED: ORACLE_PASSWORD is not set.")
        sys.exit(1)
    print(f"  OK: ORACLE_USER={user!r} is set, ORACLE_PASSWORD is set "
          f"({len(password)} chars).")

    dsn = args.dsn or os.environ.get("ORACLE_DSN")
    if not dsn:
        print("  FAILED: no DSN. Pass --dsn hostname:port/service_name or "
              "set ORACLE_DSN.")
        sys.exit(1)
    print(f"  OK: DSN={dsn!r}")

    print("\nStep 2: importing oracledb...")
    try:
        import oracledb
    except ImportError:
        print("  FAILED: oracledb is not installed in this interpreter.")
        print("  Fix: pip install oracledb")
        print("  If using PyCharm: check the Python interpreter selected in "
              "your Run Configuration matches the environment where you "
              "installed it.")
        sys.exit(1)
    print(f"  OK: oracledb version {oracledb.__version__}")

    print(f"\nStep 3: connecting to Oracle as {user} ...")
    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
    except Exception as e:
        print(f"  FAILED to connect: {type(e).__name__}: {e}")
        print("\n  Common causes:")
        print("  - Wrong DSN format (should be hostname:port/service_name)")
        print("  - VPN not connected, if the DB is on a private network")
        print("  - Firewall blocking the port (often 1521)")
        print("  - Wrong username/password")
        print("  - DB requires a wallet/TLS config thin mode doesn't have "
              "-- ask your DBA if 'thick mode' is required")
        sys.exit(1)
    print("  OK: connected successfully.")

    print("\nStep 4: running a trivial query (SELECT 1 FROM DUAL)...")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM DUAL")
        result = cursor.fetchone()
        print(f"  OK: query returned {result}")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        conn.close()
        sys.exit(1)

    if args.table:
        print(f"\nStep 5: running SELECT COUNT(*) FROM {args.table} ...")
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {args.table}")
            count = cursor.fetchone()[0]
            print(f"  OK: {args.table} has {count:,} rows.")
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            print("  Common causes: wrong table name, wrong schema prefix, "
                  "or your ORACLE_USER doesn't have SELECT grant on this table.")
            conn.close()
            sys.exit(1)

    conn.close()
    print("\nAll checks passed. The connection itself is good -- if "
          "01_build_panel.py still fails, the issue is in --tables / "
          "--table-prefix arguments or column names, not connectivity.")


if __name__ == "__main__":
    main()

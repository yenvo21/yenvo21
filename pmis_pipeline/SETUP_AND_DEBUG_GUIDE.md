# PMIS Pipeline: Setup and Debugging Guide

This guide takes you from an empty folder to a final, verified dataset. Work through the phases in order. Each phase ends with a **Done when** check. Don't move on until it passes, because problems found early are much easier to fix than problems found in the final table.

| Phase | Goal | Time |
|---|---|---|
| 0 | Install the tools | 30 min |
| 1 | Prove Python can reach Oracle | 15 min |
| 2 | Match the column names | 30 min |
| 3 | Small debug run (1–2 years, 1–2 routes) | 30 min |
| 4 | Trace known segments by hand | 1–2 h |
| 5 | Fix the treatment rules with FME | 2–4 h |
| 6 | Full run and automatic checks | 1 h |
| 7 | Reconcile with the engineer's results | 2–4 h |
| 8 | Freeze the final version | 30 min |

---

## Phase 0: Install the tools

**1. Install Python 3.10 or newer.** Tick **"Add python.exe to PATH"** during installation. Check it in Command Prompt:

```
python --version
```

**2. Install VS Code** (recommended for debugging) and the **Python** extension by Microsoft.

**3. Create the project and virtual environment:**

```
mkdir C:\projects\pmis_pipeline
cd C:\projects\pmis_pipeline
```

Copy all pipeline files into this folder, then run:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**4. In VS Code**, open the folder with **File → Open Folder → `C:\projects\pmis_pipeline`**. Then press `Ctrl+Shift+P` → **Python: Select Interpreter** and choose the one with `.venv` in its path.

**5. Run the demo** in a separate data folder, so fake data never mixes with real data:

```
set PMIS_DATA_DIR=C:\projects\pmis_demo_data
python run_pipeline.py --demo
python debug_checks.py
```

**Done when:** the demo prints 8 numbered steps, and `debug_checks.py` shows no FAIL.

| Problem | Fix |
|---|---|
| `python` not recognized | Reinstall Python with "Add to PATH" ticked, then open a new Command Prompt. |
| `pip install` SSL or connection error | Corporate proxy. Ask IT for the address, then use `pip install --proxy http://proxy:port -r requirements.txt`. |
| `No module named pandas` | The virtual environment isn't active. Run `.venv\Scripts\activate` first. |

---

## Phase 1: Prove Python can reach Oracle

Set the connection details for this session. Get the DSN from the FME workspace's Oracle reader, your `tnsnames.ora` file, or your DBA.

```
set PMIS_DATA_DIR=C:\projects\pmis_data
set PMIS_USER=your_username
set PMIS_PASSWORD=your_password
set PMIS_DSN=dbhost:1521/servicename
set PMIS_TABLE=PMIS
python test_connection.py
```

If the data is stored as one table per year (for example `PMIS_2016`, `PMIS_2017`), use:

```
set PMIS_TABLE=PMIS_{year}
```

**Done when:** it prints "Connected" plus a row count for every year from 2016 to 2025.

| Error | Meaning | Fix |
|---|---|---|
| `ORA-01017` | Wrong username or password | Check the credentials; test them in SQL Developer or Toad. |
| `ORA-12514` | Wrong service name | Fix the part after `/` in the DSN. |
| `DPY-6005`, timeout | Can't reach the server | Connect to VPN; check the host and port. |
| `DPY-3010`, `DPY-3015` | Older database needs "thick mode" | Install Oracle Instant Client and add `oracledb.init_oracle_client(lib_dir=r"C:\oracle\instantclient_23_x")` before connecting in `extract.py` and `test_connection.py`. |
| `ORA-00942` | Table not found | Check `PMIS_TABLE`. You may need the schema prefix, e.g. `PMISOWNER.PMIS`. |

**Tip:** compare the row counts with what you see in Power BI or SQL Developer. Write them down; you'll use them again in Phase 3.

---

## Phase 2: Match the column names

`test_connection.py` also lists the expected columns it could not find. Common reasons:

- **Different naming:** `LAYR1` vs `LAYR_1`. Fix the pattern in `config.py` (`LAYER_COLS`).
- **Retired or renamed columns:** check the metadata workbook for the column's `EFFECTIVE YEARS`.
- **Columns that only exist in some years** (e.g. `STRUC_C_PCT` before 2017) are fine. The pipeline fills them as blank.

**Done when:** the only missing columns are ones you have deliberately accepted as missing, and you've written down why.

---

## Phase 3: Small debug run

Never debug on the full dataset: runs are slow and errors are buried. Use two recent years and one or two routes you know well:

```
python run_pipeline.py --years 2024 2025 --routes 035 080
```

Then check the results:

```
python debug_checks.py
```

**What to look at:**

1. **Row counts** in the printed lineage (steps 01–08). Does step 01 match your Phase 1 counts for those routes? Does any step lose far more rows than expected?
2. **`CAPDAT parses as date`.** If this warns, look at the sample values it prints and change `dayfirst=True` in `transform.py` (`harmonize`) to match the actual format.
3. **`ORIGKEY length = 19`.** If it fails, ORIGKEY may have spaces or a different structure. That breaks the `SYSTEM` recovery; check `harmonize` in `transform.py`.

**Using the VS Code debugger** (the fastest way to see what's happening inside a step):

1. Open `transform.py` and click left of a line number to set a red **breakpoint**, e.g. on the `return` line of `align_segments`.
2. Open `run_pipeline.py`, press `F5`, and choose **Python File**. To pass the debug arguments, create `.vscode/launch.json` (VS Code offers to do this) with:

   ```json
   {
     "version": "0.2.0",
     "configurations": [{
       "name": "Debug pipeline",
       "type": "debugpy",
       "request": "launch",
       "program": "run_pipeline.py",
       "args": ["--years", "2024", "2025", "--routes", "035"],
       "env": {"PMIS_DATA_DIR": "C:\\projects\\pmis_data"},
       "console": "integratedTerminal"
     }]
   }
   ```

3. When execution stops at the breakpoint, open the **Debug Console** and inspect the data directly, e.g. `out.head()`, `out.describe()`, `len(out)`.
4. Press `F10` to step one line, `F5` to continue.

**Done when:** the small run finishes with no FAIL, and the row counts at each step make sense to you.

---

## Phase 4: Trace known segments by hand

This is the most valuable debugging step. Pick **3–5 segments you can verify independently**:

- One with a known overlay or resurfacing during 2016–2025.
- One reconstructed during 2016–2025.
- One untouched the whole period.
- One on a route that was re-segmented (different ORIGKEYs in different years).

For each one, run:

```
python debug_checks.py --trace <ORIGKEY from the base year>
```

The trace shows four things in order:

1. The segment's attributes and assigned treatment.
2. Every raw row that overlaps it, in every year.
3. The aligned, length-weighted values.
4. The final model rows with age.

**Check against reality:**

- Does the treatment year match the project history? Open the **Road Analyzer** or **Pathweb** hyperlink for that segment.
- Does IRI drop sharply in the year after the treatment, as it should?
- Do the aligned values sit between the raw values of the pieces they came from?
- Are the rows before the treatment excluded from step 4?

**Done when:** all traced segments make engineering sense. Save the trace output; it becomes the worked example in the documentation.

---

## Phase 5: Fix the treatment rules with FME

The treatment logic in `transform.py` (`derive_treatment`) is a **draft**. Replace it with the engineer's real rules:

1. In the FME workspace, find the transformers that assign treatment codes (see the earlier `scan_fme_workspace` helper). Look for thickness cutoffs, project-type conditions, and `CIP` base type.
2. Update the thresholds in `config.py` (`FUNC_MAX_IN`, `STR1_MAX_IN`) and the conditions in `derive_treatment`.
3. Rerun the small debug run and check `qc/treatment_counts.csv`.
4. Change `TREATMENT_RULE` from `"DRAFT - verify against FME"` to something like `"FME rules, verified <date>"`.

**Done when:** `UNKNOWN` treatments are below about 10%, and each remaining `UNKNOWN` has an understood reason.

---

## Phase 6: Full run and automatic checks

```
python run_pipeline.py --force-extract
python debug_checks.py
```

`--force-extract` makes sure all years are pulled fresh from Oracle. Expect the first extraction to take a while; later runs reuse the files in `01_raw`.

**Review every WARN:**

| Check | If it warns |
|---|---|
| Share of rows dropped | Open `qc/dropped_by_reason.csv`. A spike in one year usually means a collection issue that year. Ask the pavement team. |
| Segments ≥ 90% covered | Gaps in the linear referencing. Trace a few low-coverage segments. |
| Segments per year stable | A year with far fewer segments may have missing LRS data. |
| Distress value ranges | Check whether the units changed or there are data-entry errors; adjust `RANGES` in `debug_checks.py` if the engineers confirm other limits. |
| Observations per segment | Expected for recently treated roads. Those will need Family models. |

**Done when:** no FAIL, and every WARN is either fixed or explained in writing.

---

## Phase 7: Reconcile with the engineer's results

Before trusting the new data, compare it with what the engineer's FME process produced:

1. **Counts:** for the same distress and years, compare COUNT per segment with his model table, using `reconcile_counts()` from `pmis_forensics.py`.
2. **Treatments:** compare `qc/treatment_counts.csv` with the treatment distribution in his Power BI.
3. **Spot checks:** for the Phase 4 segments, compare his fitted curve with your data points.

Differences aren't automatically errors: your pipeline may be deliberately stricter (e.g. dropping `X` data). But every difference should be explained, and the explanations belong in the documentation.

**Done when:** the large majority of segments match, and the mismatches fall into a few understood categories.

---

## Phase 8: Freeze the final version

1. **Save the code in Git**, even locally. It gives you a history of every change.

   ```
   git init
   git add *.py *.md requirements.txt
   git commit -m "PMIS pipeline v1.0 - verified against FME"
   ```

2. **Record the version** in a short text file next to the data: date, Git commit, years included, the settings in `config.py`, and the final row counts from `qc/lineage.csv`.
3. **Keep a copy** of the final `03_model` and `qc` folders under a dated name, e.g. `pmis_data_v1_2026-10`.
4. **Connect Power BI** to `03_model` (or to the Oracle tables loaded with `write_oracle()`).

**Done when:** someone else could rerun the pipeline from the Git commit and the version note and get the same row counts.

---

## Sign-off checklist

- [ ] Oracle row counts per year recorded (Phase 1)
- [ ] All column-name differences resolved or documented (Phase 2)
- [ ] Small debug run clean (Phase 3)
- [ ] 3–5 segments traced and confirmed against Road Analyzer / Pathweb (Phase 4)
- [ ] Treatment rules replaced with verified FME logic (Phase 5)
- [ ] Full run: no FAIL, all WARN explained (Phase 6)
- [ ] Differences from the engineer's results explained (Phase 7)
- [ ] Code committed and data version recorded (Phase 8)

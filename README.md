# EAMS Automation Pipeline

Automates case identifier retrieval from California's EAMS (Electronic Adjudication Management System) workers' compensation portal.

**5 hours of manual work → 30 minutes, unattended.**

---

## The Problem

Medical lien management firms spend hours every day on a repetitive task:
- Search California's EAMS portal for client names
- Click through result pages one by one
- Manually copy ADJ (case) numbers
- Save results to spreadsheets

**At scale:** 50–60 records per day × 5 hours per person = significant overhead.

## The Solution

A single-file executable that processes batches of 100+ records automatically:

✅ Reads patient records from CSV  
✅ Searches EAMS portal for each record  
✅ Extracts all associated ADJ numbers  
✅ Saves results live (crash-safe)  
✅ Handles rate limiting and session drops silently  

No Python install required. No IT tickets. Just run the `.exe`.

---

## Quick Start

### 1. Prepare Your CSV

```
First Name,Last Name,DOB
John,Doe,01/15/1985
Jane,Smith,03/22/1990
```

DOB is optional. Column header names are flexible (firstname, first_name, First Name all work).

### 2. Run the Executable

Place `EAMS_FINAL.exe` and your CSV file in the same directory. Double-click the `.exe`.

Choose **Mode 2** (Batch CSV) and enter your filename.

### 3. Review Results

Each record gets its own output file:

```
extracted_cases_DOE_JOHN_it_8.txt

EAMS CASE RETRIEVAL REPORT (LIVE PROGRESS SAVE)
Target profile: JOHN DOE
DOB context: 01/15/1985
----------------------------------------
Discovered Case Identifiers (5 total):
[1] ADJ19193456
[2] ADJ19193475
[3] ADJ19193489
[4] ADJ19193868
[5] ADJ19352897
```

---

## How It Works

### Run Modes

**Mode 1: Single Record**  
Enter one first name, last name, and optional DOB for a one-off lookup.

**Mode 2: Batch CSV**  
Load a CSV file with multiple records and process all of them sequentially without further input.

### Rate Limiting & Resilience

The EAMS portal enforces aggressive rate limiting (HTTP 429). This pipeline handles it automatically:

- **Exponential backoff** — wait intervals double on repeated throttles (5s → 10s → 20s)
- **Session recovery** — detects when the portal kicks you back to login and re-authenticates silently
- **Index-based retry** — if a click fails, it retries the same record, never skips
- **Live progress saves** — each completed record is written to disk immediately

If something goes wrong mid-run, your data is safe. Resume by re-running the same CSV.

### DOB Intelligence (v1.0.1)

If a search returns 0 results, the pipeline automatically retries up to 3 times **without** DOB:

- Each retry includes a 10-second pause
- Full re-authentication between attempts
- Prevents false negatives from malformed DOB data

### Memory Stability (v1.0.1)

Real-time memory monitoring with automatic garbage collection:

- Warnings at 1GB and 2GB thresholds
- Page reload between records
- Tested stable at 1000+ records
- Typical usage: <100MB

---

## Scaling to Multiple Agents

No shared server, no database, no coordination needed.

Split your records into separate CSV files and assign one agent per file:

| Agent | CSV | Records |
|-------|-----|---------|
| Agent 1 | batch1.csv | 1–100 |
| Agent 2 | batch2.csv | 101–200 |
| Agent 3 | batch3.csv | 201–300 |

All three run simultaneously. 300 records in ~30 minutes (same time as 100).

Why this scales cleanly:
- Each agent runs fully independently
- One agent crashing doesn't affect others
- Crash-safe design means at most one record is lost, never the whole batch
- Zero setup — just `.exe` + CSV

---

## Technical Stack

- **Python 3** — core automation logic
- **Playwright** — browser automation (non-headless; you see the browser during execution)
- **PyInstaller** — single-file `.exe` with bundled Chromium (no external dependencies)
- **CSV / Regex** — input parsing and ADJ number extraction
- **psutil** — memory monitoring

---

## Build from Source

```bash
pip install -r requirements.txt
playwright install chromium
pyinstaller --onefile --name EAMS_Automation_v1.0.1 EAMS_FINAL.py
```

Executable appears in `dist/` folder. (~250–300MB, includes Chromium)

---

## Real-World Examples

### Scenario: Incorrect DOB in CSV
```
Initial search returned 0 result(s).
[RETRY 1/3] No results found with DOB. Retrying without DOB...
[RETRY 2/3] Search without DOB returned 28 result(s).
[RETRY SUCCESS] Found 28 result(s) without DOB.
```

### Scenario: Rate Limited During Processing
```
[ALERT] HTTP 429 Rate Limit hit! Waiting 5 seconds...
[ALERT] HTTP 429 Rate Limit hit! Waiting 10 seconds...
[SUCCESS] Rate limit cleared. Session recovered.
```

### Scenario: Portal Session Drop
```
Gateway detected at match 47. Re-authenticating...
[SESSION RECOVERY] Portal session expired.
Search restored. Continuing from match 47.
```

---

## Notes

- Built independently in one week (5th semester CS undergrad)
- EAMS is a public California government portal — no private credentials required
- Input CSVs with real patient data are not included (privacy)
- Sample outputs use placeholder ADJ numbers
- `.exe` build is ~250–300MB (includes Chromium browser)

---

## Version History

**v1.0.1** (Current)
- Memory leak fixed — stable at 1000+ records
- DOB retry logic — 3 automatic retries without DOB if initial search fails
- Improved 429 handling with exponential backoff
- Session recovery detection at three checkpoints per record
- Better error messages and recovery logging

**v1.0.0**
- Initial release
- Basic search and extraction
- Single retry attempt

---

## Download

Pre-built executable available on the **[Releases](https://github.com/M-zaid-bilal/EAMS_Automation/releases)** page.

---

## Questions?

This tool is designed to be self-explanatory. The `.exe` walks you through each step. If you hit anything unclear, open an issue or reach out directly.
# EAMS Automation Pipeline

> Automated case identifier retrieval from the California EAMS (Electronic Adjudication Management System) workers' compensation portal — reducing a ~5 hour daily manual process to ~30 minutes, unattended.

## Impact

| Before | After |
|--------|-------|
| **Records processed** | 50–60 per day (manual) | 100 per run (automated) |
| **Time required** | ~5 hours/day per staff member | ~30 minutes unattended |
| **Time saved** | — | ~4.5 hours/day |
| **Dependencies to run** | Staff computer + training | Zero — standalone `.exe` |
| **Failure handling** | Manual retry | Automatic recovery |

## What It Does

Given a CSV of client records, the pipeline:

1. Reads each record (first name, last name, DOB)
2. Navigates the EAMS portal gateway and submits a case participant search
3. Iterates through all matching result rows, clicking into each detail page
4. Extracts all associated ADJ numbers via regex across the full page HTML
5. Saves a structured output file per record in real time (crash-safe)
6. Moves to the next record automatically

Each output file is named `extracted_cases_LASTNAME_FIRSTNAME_it_N.txt` and contains all discovered case identifiers for that individual. The `it_N` suffix tracks the iteration/run version.

**Sample output:**

```
EAMS CASE RETRIEVAL REPORT (LIVE PROGRESS SAVE)
Target profile: JOHN DOE
DOB context: [REDACTED]
----------------------------------------
Discovered Case Identifiers (2 total):
[1] ADJ00000001
[2] ADJ00000002
```

## Run Modes

The pipeline offers two modes selected at startup:

### Mode 1 — Single Record (Manual Entry)

Prompts for first name, last name, and optional DOB. Useful for one-off lookups or testing.

### Mode 2 — Batch CSV (Bulk Ingest)

Reads a CSV file from the same directory. Queues all records and processes them sequentially without further input.

**CSV format:**

```csv
First Name,Last Name,DOB
John,Doe,01/15/1985
Jane,Smith,03/22/1990
```

The column header parser is flexible — it strips spaces, underscores, and hyphens and matches case-insensitively, so minor formatting variations in the CSV header are handled automatically. `First Name`, `firstname`, `first_name` all resolve correctly.

DOB is optional per record. If a search returns multiple matches and no DOB was provided, the pipeline pauses and prompts the operator to enter one for refinement before continuing.

## Technical Highlights

### Dethrottling & 429 Handling

The EAMS portal enforces aggressive rate limiting with no documented retry-after headers. The pipeline handles this through a multi-layer strategy:

- **Exponential backoff** — wait intervals double progressively on repeated 429 responses (5s → 10s → 20s)
- **UI reload** — attempts to click the portal's own reload button first
- **Hard script reset** — injects `window.location.reload()` directly if the UI button is unresponsive
- **Live progress save** — every completed record is written to disk immediately, so a crash or forced reset never loses prior work

### Session Recovery & Gateway Re-authentication

The EAMS portal silently drops sessions mid-run and redirects to a login gateway. The pipeline detects this at three checkpoints per record — before clicking a result, after clicking, and after navigating back — and automatically re-authenticates and restores the search without operator intervention.

### Result Loop Architecture

The core traversal loop uses index-based retry logic rather than sequential advancement. If a 429 or session drop occurs mid-click, the same result index is retried rather than skipped, ensuring no case record is missed.

### DOB Retry Logic (v1.0.1)

If a search with DOB returns 0 results, the pipeline automatically retries up to 3 times without DOB:

- Each retry includes a 10-second pause
- Full re-authentication between attempts
- If successful, DOB is marked as None for output
- Prevents false negatives from incorrect or malformed DOB data

### Memory Monitoring (v1.0.1)

Real-time memory tracking with automatic garbage collection:

- Warnings at 1GB and 2GB thresholds
- Page reload between records to prevent memory accumulation
- Stable performance even at 1000+ records
- Memory usage typically stays under 100MB

### Standalone Executable

Packaged with PyInstaller via Auto-py-to-exe into a single `.exe` with no external dependencies. Runs on any Windows machine with zero setup — no Python install, no pip, no IT involvement required.

## Stack

- **Python 3**
- **Playwright** — browser automation against the EAMS portal (non-headless; browser window visible during run)
- **PyInstaller** — packaging engine for the standalone executable
- **Auto-py-to-exe** — GUI frontend for configuring and running PyInstaller
- **CSV / file I/O** — input parsing and live output saving
- **re (regex)** — ADJ number extraction from raw page HTML
- **psutil** — memory monitoring and garbage collection

## Repository Structure

```
├── EAMS_FINAL.py              # Main script (v1.0.1)
├── requirements.txt           # Python dependencies
├── Sample_file.csv            # Example input template
├── sample_output/
│   ├── extracted_cases_DOE_JOHN_sample.txt
│   ├── extracted_cases_SMITH_JANE_sample.txt
│   └── extracted_cases_ROE_RICHARD_sample.txt
└── README.md
```

## Version History

### v1.0.1 (Current)
- Memory leak fixed — stable at 1000+ records
- DOB retry logic — 3 attempts without DOB if initial search fails
- Improved 429 handling with exponential backoff
- Self-healing session recovery
- Memory monitoring with automatic GC
- Better error messages and recovery logging

### v1.0.0
- Initial release
- Basic search and extraction
- Single retry attempt

## Scalability — Distributed Workflow

The pipeline scales horizontally across multiple agents with zero additional infrastructure.

Each agent runs the same `.exe` independently on their own machine with their own CSV slice of records. No shared server, no database, no network configuration required.

**Example distribution:**

| Agent | CSV Input | Records |
|-------|-----------|---------|
| Agent 1 | `agent1_cases.csv` | Records 1–100 |
| Agent 2 | `agent2_cases.csv` | Records 101–200 |
| Agent 3 | `agent3_cases.csv` | Records 201–300 |

All three run simultaneously. 300 records processed in ~30 minutes — the same time a single agent takes for 100.

**Why this works cleanly:**

- **No bottleneck** — agents run fully independently with no coordination overhead
- **Fault isolation** — if one machine crashes, only that agent's batch is affected; others continue uninterrupted
- **Crash-safe by design** — live progress saving means even a mid-run crash loses at most one record, not the entire batch
- **Data privacy** — each agent only sees their own assigned records
- **Zero onboarding** — a new agent needs only the `.exe` and their CSV; no setup, no installation, no tooling training required

**To prepare a CSV slice:**

Split the master records file into batches of the desired size and assign one file per agent. The CSV header parser handles minor formatting differences automatically.

## Recovery Examples (Real Test Results)

### Scenario 1: Incorrect DOB in CSV
```
Initial search returned 0 result(s).
[RETRY 1/3] No results found with DOB. Retrying without DOB...
[RETRY 2/3] Search without DOB returned 28 result(s).
[RETRY SUCCESS] Found 28 result(s) without DOB.
```

### Scenario 2: Rate Limit During Processing
```
[ALERT] HTTP 429 Rate Limit hit! Waiting 5 seconds...
[ALERT] HTTP 429 Rate Limit hit! Waiting 10 seconds...
[SUCCESS] Rate limit cleared.
Processing continued from same record.
```

### Scenario 3: Portal Session Drop
```
Gateway detected, re-authenticating...
[SESSION RECOVERY] Portal session expired - re-authenticating...
Search restored. Continuing from same record.
```

## Notes

- Built independently in one week during a job placement (5th semester CS undergrad)
- The EAMS portal is a public California government endpoint (`eams.dwc.ca.gov`); no private credentials are required or stored
- Gateway form fields use placeholder values that satisfy the portal's requester information form
- Input CSV and real case outputs are not included in this repository — sample outputs use placeholder names and dummy ADJ numbers
- The `.exe` build is ~250-300MB (includes Chromium browser); download from Releases page

## Build from Source

```bash
pip install -r requirements.txt
playwright install chromium
pyinstaller --onefile --name EAMS_Automation_v1.0.1 EAMS_FINAL.py
```

The compiled executable will appear in the `dist/` folder. Place your input CSV in the same directory as the `.exe` before running.

## Download

Pre-built executable available on the [Releases](https://github.com/M-zaid-bilal/EAMS_Automation/releases) page.
```

## Key Changes Made

| Section | What Was Added |
|---------|----------------|
| Impact table | Added "Failure handling" row |
| Technical Highlights | Added DOB Retry Logic + Memory Monitoring subsections |
| Repository Structure | Updated to v1.0.1 file names |
| Version History | New section showing v1.0.0 vs v1.0.1 |
| Recovery Examples | New section with real test scenarios |
| Build from Source | Updated to v1.0.1 naming |
| Download | New section pointing to Releases |

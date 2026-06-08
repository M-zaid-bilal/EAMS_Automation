# EAMS Automation Pipeline

> Automated case identifier retrieval from the California EAMS (Electronic Adjudication Management System) workers' compensation portal — reducing a ~5 hour daily manual process to ~30 minutes, unattended.

---

## Impact

| | Before | After |
|---|---|---|
| **Records processed** | 50–60 per day (manual) | 100 per run (automated) |
| **Time required** | ~5 hours/day per staff member | ~30 minutes unattended |
| **Time saved** | — | ~4.5 hours/day |
| **Dependencies to run** | Staff computer + training | Zero — standalone `.exe` |

---

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

---

## Run Modes

The pipeline offers two modes selected at startup:

### Mode 1 — Single Record (Manual Entry)
Prompts for first name, last name, and optional DOB. Useful for one-off lookups or testing.

### Mode 2 — Batch CSV (Bulk Ingest)
Reads a CSV file from the same directory. Queues all records and processes them sequentially without further input.

**CSV format:**
```
First Name,Last Name,DOB
John,Doe,01/15/1985
Jane,Smith,03/22/1990
```

The column header parser is flexible — it strips spaces, underscores, and hyphens and matches case-insensitively, so minor formatting variations in the CSV header are handled automatically. `First Name`, `firstname`, `first_name` all resolve correctly.

DOB is optional per record. If a search returns multiple matches and no DOB was provided, the pipeline pauses and prompts the operator to enter one for refinement before continuing.

---

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

### Standalone Executable
Packaged with PyInstaller via Auto-py-to-exe into a single `.exe` with no external dependencies. Runs on any Windows machine with zero setup — no Python install, no pip, no IT involvement required.

---

## Stack

- **Python 3**
- **Playwright** — browser automation against the EAMS portal (non-headless; browser window visible during run)
- **PyInstaller** — packaging engine for the standalone executable
- **Auto-py-to-exe** — GUI frontend for configuring and running PyInstaller
- **CSV / file I/O** — input parsing and live output saving
- **re (regex)** — ADJ number extraction from raw page HTML

---

## Repository Structure

```
├── Automation_EAMS.py         # Main script
├── requirements.txt           # Python dependencies
├── sample_output/
│   ├── extracted_cases_DOE_JOHN_sample.txt
│   ├── extracted_cases_SMITH_JANE_sample.txt
│   └── extracted_cases_ROE_RICHARD_sample.txt
└── README.md
```

---

## Scalability — Distributed Workflow

The pipeline scales horizontally across multiple agents with zero additional infrastructure.

Each agent runs the same `.exe` independently on their own machine with their own CSV slice of records. No shared server, no database, no network configuration required.

**Example distribution:**

| Agent | CSV Input | Records |
|---|---|---|
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

---

## Notes

- Built independently in one week during a job placement (5th semester CS undergrad)
- The EAMS portal is a public California government endpoint (`eams.dwc.ca.gov`); no private credentials are required or stored
- Gateway form fields use placeholder values that satisfy the portal's requester information form
- Input CSV and real case outputs are not included in this repository — sample outputs use placeholder names and dummy ADJ numbers
- The `.exe` build is not included due to file size (~228MB); build from source using the commands below

---

## Build from Source

```bash
pip install -r requirements.txt
playwright install chromium
pyinstaller --onefile Automation_EAMS.py
```

The compiled executable will appear in the `dist/` folder. Place your input CSV in the same directory as the `.exe` before running.

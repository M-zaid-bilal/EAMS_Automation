# EAMS Automation Pipeline

Automates case identifier retrieval from California's EAMS (Electronic Adjudication Management System) workers' compensation portal.

**5 hours of manual work → 30 minutes, unattended.**

---

# The Problem

Medical lien management firms spend hours every day on a repetitive task:

- Search California's EAMS portal for client names
- Click through result pages one by one
- Manually copy ADJ (case) numbers
- Save results to spreadsheets

At scale:

> 50–60 records per day × 5 hours per person = significant overhead.

---

# The Solution

A single-file executable that processes batches of **100+ records automatically**:

- ✅ Reads patient records and advanced optional search/detail filters from CSV
- ✅ Searches EAMS portal for each record automatically
- ✅ Gracefully handles multi-grid results using fuzzy-matching filters
- ✅ Extracts all associated and matched ADJ numbers
- ✅ Saves results live (crash-safe & real-time write-outs)
- ✅ Handles rate limiting (HTTP 429) and session drops silently

No Python install required. No IT tickets. Just run the `.exe`.

---

# Download

The fully packaged standalone executable is ready to run out of the box with zero dependencies (Chromium is bundled inside!).

🚀 **Download the Latest Release**  
`EAMS_Automation_v1.0.2.exe`

---

# Quick Start

## 1. Prepare Your CSV

Column header names are highly flexible. The parser strips punctuation, spaces, and casing. You can supply simple inputs or use advanced filters.

```csv
First Name,Last Name,DOB,employerfilter,injurydatefilter,cityfilter
Rafael,Chavez,02/20/1981,,,
John,Doe,,Boston Scientific,2019,Los Angeles
Jane,Smith,03/22/1990,,01/01/2018,
```

### Required columns

- First Name
- Last Name
- DOB

(DOB may be empty, but the column must exist.)

### Optional columns

- employerfilter
- injurydatefilter
- cityfilter
- zipfilter

---

## 2. Run the Executable

Place the downloaded executable and your CSV file in the same directory.

```text
EAMS_Automation_v1.0.2.exe
```

Double-click the executable.

Choose:

```text
Mode 2 (Batch CSV)
```

Enter your filename:

```text
SAMPLE_PATIENT.csv
```

---

## 3. Review Results

Each record gets its own live progress save file.

Example:

```text
extracted_cases_Chavez_Rafael_it_15.txt
```

Example output:

```text
EAMS CASE RETRIEVAL REPORT (LIVE PROGRESS SAVE)

Target profile: Rafael Chavez
DOB context: 02/20/1981
Active filters: InjuryDate~'2019'

----------------------------------------

Discovered Case Identifiers (2 total):

[1] ADJ12738574
[2] ADJ15602252
```

---

# Core Features & Intelligence

## 1. Result Filter Engine (Fuzzy Matching)

To navigate complex search results with high-volume rows, the script applies targeted refinements.

### Fuzzy Employer Match

Resolves spelling variations and layout disparities.

Examples:

```text
Boston Scientific Corp
```

matches

```text
Corp of Boston Scientific
```

using tokenized overlap while ignoring common stopwords:

- LLC
- Inc
- Co
- The

### Smart Injury Date Match

Handles:

- Single year matches (`2019`)
- Exact dates (`12/30/2008`)
- Continuous Trauma (CT) ranges

Example:

```text
01/01/2019 - 03/05/2021
```

If a filter year falls within a CT boundary range, the row is accepted automatically.

---

## 2. Interactive CLI Refinement

If a batch run encounters multiple matching records and no DOB or filters were supplied, the script pauses and offers refinement options.

Available prompts:

```text
Enter DOB
Enter Employer Filter
Enter Injury Date Filter
Enter City
Enter ZIP Code
```

Or simply press:

```text
[ENTER]
```

to crawl and scrape all detected rows.

---

## 3. Rate Limiting & Resilience

The EAMS portal enforces aggressive rate limiting (`HTTP 429`).

The pipeline automatically handles this through:

### Exponential Backoff

Automatically pauses and retries:

```text
5s → 10s → 20s
```

before refreshing.

### Session Recovery

Detects logouts and:

- Returns to the secure gateway
- Re-authenticates
- Restores the active search

### Live Progress Saves

Writes extraction results immediately so crashes never destroy previous work.

---

## 4. DOB Automatic Fallback

If searching with a DOB returns zero results, the engine automatically retries.

Process:

1. Clear DOB
2. Re-authenticate if required
3. Retry search

Up to:

```text
3 attempts
```

This handles situations where DOB data in EAMS is incomplete or inconsistent.

---

## 5. Memory Stability Engine

Because PyInstaller builds run in a persistent browser session, memory usage is actively monitored.

Features:

- Regular RSS RAM monitoring
- CLI memory diagnostics
- Automatic garbage collection

Triggers:

```text
1 GB warning threshold
2 GB emergency threshold
```

using:

```python
gc.collect()
```

Typical runtime memory usage remains:

```text
< 100 MB
```

---

# Deployment & Multi-Agent Scaling

To run multiple extraction jobs simultaneously, split records across separate CSV files.

| Agent | Target CSV | Range | Execution |
|---------|---------|---------|---------|
| Agent 1 | batch_1.csv | Records 1–100 | Running locally |
| Agent 2 | batch_2.csv | Records 101–200 | Running locally |
| Agent 3 | batch_3.csv | Records 201–300 | Running locally |

Because each instance maintains independent local state:

- No database locks
- No coordination overhead
- No network race conditions

---

# Build From Source

Compile the script into a completely self-contained executable with Playwright Chromium bundled.

## 1. Configure the Environment

### Windows Command Prompt

```cmd
set PLAYWRIGHT_BROWSERS_PATH=0
```

### Windows PowerShell

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH=0
```

### macOS / Linux

```bash
export PLAYWRIGHT_BROWSERS_PATH=0
```

---

## 2. Install Packages & Browser Bundle

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 3. Compile via PyInstaller

```bash
pyinstaller --onefile ^
  --add-data ".venv/Lib/site-packages/playwright/driver;playwright/driver" ^
  --name EAMS_Automation_v1.0.2 ^
  EAMS_refined_gemini_pro.py
```

### Linux/macOS Example

```bash
pyinstaller --onefile \
  --add-data ".venv/Lib/site-packages/playwright/driver:playwright/driver" \
  --name EAMS_Automation_v1.0.2 \
  EAMS_refined_gemini_pro.py
```

> Adjust the `.venv` path if your environment uses a different directory name such as `env/` or a Conda environment.

The compiled executable will appear in:

```text
dist/
```

Approximate size:

```text
250–300 MB
```

(includes Chromium)

---

# Version History

## v1.0.2 (Current — it_15 Release)

### Result Filter Engine

- Added token-based fuzzy employer matching
- Added CT date-range parsing

### Dynamic CLI Prompts

- Interactive filtering during multi-grid matches

### Flexible Headers

- Dynamic mapping of optional CSV parameters

### Improved Logging

- Displays active filters and runtime status

### Distribution Polish

- Official self-contained executable release

---

## v1.0.1

### Memory Fix

- Added memory tracking
- Added forced garbage collection

### DOB Retry

- Added 3-strike DOB fallback logic

### Rate Limit Adjustments

- Added exponential backoff handling

---

## v1.0.0

Initial release.

Features included:

- Standard search automation
- Search grid traversal
- ADJ extraction
- File export structure

---

# Questions & Support

This script runs entirely locally on your machine.

For performance diagnostics, monitor the real-time memory logs displayed in the console:

```text
[MEMORY]
```

These outputs provide visibility into runtime memory consumption and automatic cleanup activity.

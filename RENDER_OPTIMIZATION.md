# Render Server Optimization — Implementation Plan & Progress

> **Goal:** Make the SGBAU scraper survive 10,000 results within Render's 512 MB RAM limit  
> **AND** be resilient during high-traffic result declaration periods.  
> **Created:** 2026-09-03

---

## Current Problems

1. **Pandas imports ~120 MB** just by existing — overkill for CSV writing
2. **15s / 20s timeouts** — server takes 45-180s during peak traffic → instant crash
3. **No retries** — one timeout = permanent failure
4. **CSRF token fetched once** — can expire during long batch runs
5. **50 concurrent connections** during watcher batch — hammers the overloaded server
6. **All results held in memory** — duplicated across `JOBS[]` and `dept_results[]`

---

## Phase Overview

| Phase | What | Files Changed | RAM Saved | Status |
|---|---|---|---|---|
| **1** | Drop Pandas → csv stdlib | `utils.py`, `scraper.py`, `main.py`, `watcher.py`, `requirements.txt` | ~120 MB | ✅ Done |
| **2** | Increase timeouts + add tenacity retries | `scraper.py`, `watcher.py`, `requirements.txt` | — | ✅ Done |
| **3** | CSRF token auto-refresh | `scraper.py` | — | ✅ Done |
| **4** | Reduce watcher concurrency + adaptive mode | `watcher.py`, `models.py` | ~20 MB | ✅ Done |
| **5** | Stream results to temp file (optional) | `main.py`, `watcher.py` | ~50 MB | ✅ Done |
| **6** | Smoke test + verify | All | — | 🔄 In Progress |

---

## Phase 1: Drop Pandas → csv stdlib

**Impact: ~120 MB RAM saved (biggest win)**

### What Pandas does currently (and what replaces it):

| File | Current Pandas Usage | Replacement |
|---|---|---|
| `scraper.py:9` | `import pandas as pd` | Remove |
| `scraper.py:157` | `pd.DataFrame(dept_results)` → passed to `generate_class_report()` | Pass raw `list[dict]` directly |
| `utils.py:150` | `get_subject_cols(df)` uses DataFrame columns | Iterate `list[dict]` keys |
| `utils.py:183` | `generate_class_report(df, ...)` uses DataFrame ops | Pure Python loops |
| `main.py:19` | `import pandas as pd` | Remove |
| `main.py:216` | `pd.DataFrame(all_results)` for CSV export | `csv.DictWriter` |
| `watcher.py:145` | `import pandas as pd` for `build_csv_bytes()` | `csv.DictWriter` |
| `watcher.py:151` | `pd.DataFrame(results)` | `csv.DictWriter` |

### Functions to rewrite:

1. **`utils.py → get_subject_cols()`** — change from DataFrame to `list[dict]`
2. **`utils.py → generate_class_report()`** — change from DataFrame to `list[dict]`
3. **`scraper.py → scrape_departments()`** — remove DataFrame, pass raw list
4. **`main.py → download_csv()`** — use `csv.DictWriter` instead of `df.to_csv()`
5. **`watcher.py → build_csv_bytes()`** — use `csv.DictWriter`

### requirements.txt change:
```diff
 fastapi
 uvicorn[standard]
 aiohttp
 beautifulsoup4
 lxml
-pandas
 python-multipart
 sse-starlette
+tenacity
```

---

## Phase 2: Increase Timeouts + Add Tenacity Retries

**Impact: Stops crashes during high-traffic periods**

### Timeout changes:

| Location | Before | After |
|---|---|---|
| `scraper.py:32` — `init_session()` GET | 15s | 300s (5 min) |
| `scraper.py:87` — `fetch_one()` POST | 20s | 300s (5 min) |
| `telegram.py:81` — `send_message()` | 20s | 30s |
| `telegram.py:144` — `send_document()` | 30s | 60s |

### Retry logic:

- Wrap `init_session()` with `@retry(stop=stop_after_attempt(5), wait=wait_exponential_jitter(initial=5, max=120, jitter=10))`
- Wrap `fetch_one()` with retry on `TimeoutError` and `ClientError` (max 3 attempts)
- **Do NOT retry** on "Not Found / Invalid" (that's a valid response, not an error)

---

## Phase 3: CSRF Token Auto-Refresh

**Impact: Prevents mid-batch failures when token expires**

### Design:

- Pass a mutable `token_holder = {"token": str, "lock": asyncio.Lock()}` into `scrape_departments()`
- In `fetch_one()`: if response indicates token failure (HTTP 419, or server error after token was previously working), acquire the lock and call `init_session()` to refresh
- Only one concurrent request refreshes at a time (the lock prevents thundering herd)

---

## Phase 4: Reduce Watcher Concurrency + Adaptive Mode

**Impact: Prevents overwhelming the SGBAU server during peak traffic**

### Changes:

- `watcher.py:262` — reduce `workers=50` to `workers=10`
- `models.py:18` — change default `workers` from 50 to 15
- Add SSE events when retrying: `{"type": "retry", "message": "Server slow, retrying roll 25BI310387..."}`

---

## Phase 5: Stream Results to Temp File (Optional)

**Impact: ~50 MB RAM saved for large batches**

Instead of accumulating all results in `JOBS[job_id]["results"]` (a growing list), write each result to a temp CSV file as it arrives. The download endpoint reads from the file.

> This phase is optional — after Phases 1-4, we're already well within 512 MB.

---

## Phase 6: Smoke Test + Verify

- Run locally with a small batch (5-10 rolls) to verify CSV output is identical
- Check class report format matches existing output
- Verify SSE streaming still works
- Verify Telegram notification + CSV attachment still works
- Deploy to Render and confirm memory usage

---

## Projected Memory After All Phases

```
BEFORE (current):
  Base:        ~160 MB  (Python + FastAPI + pandas + numpy + aiohttp + bs4)
  10K results: ~260-345 MB peak
  
AFTER (Phase 1-4):
  Base:        ~50 MB   (Python + FastAPI + aiohttp + bs4 + tenacity)
  10K results: ~90-130 MB peak

AFTER (Phase 1-5, with streaming):
  Base:        ~50 MB
  10K results: ~60-80 MB peak
```

---

## Progress Log

| Date | Phase | Action | Result |
|---|---|---|---|
| 2026-09-03 | — | Plan created | ✅ |
| 2026-09-03 | 1 | Drop Pandas → csv stdlib | ✅ Done |
| 2026-09-03 | 2 | Increase timeouts + tenacity retries | ✅ Done |
| 2026-09-03 | 3 | CSRF token auto-refresh | ✅ Done |
| 2026-09-03 | 4 | Reduce concurrency + retry SSE events | ✅ Done |
| 2026-09-03 | 5 | Stream results to .jsonl temp file | ✅ Done |

# Session Context — Render Optimization (2026-09-03)

> **What this file is:** A complete record of everything done in the Sept 3 optimization session.
> Use this to onboard a new AI session, or as a reference for future debugging.

---

## Goal

Make the SGBAU scraper survive 10,000 results within Render's **512 MB RAM** free-tier limit,
and be resilient during high-traffic result declaration periods (when SGBAU server is overloaded).

---

## Starting Problems (Before This Session)

| # | Problem | Impact |
|---|---|---|
| 1 | `pandas` imported ~120 MB just by existing | Massive baseline RAM cost |
| 2 | 15s / 20s HTTP timeouts | SGBAU takes 45–180s during peak → instant crash |
| 3 | No retries on network failure | One timeout = permanent failure for that roll number |
| 4 | CSRF token fetched once at job start | Token can expire mid-batch → silent failures |
| 5 | 50 concurrent connections during watcher | Hammers the already-overloaded SGBAU server |
| 6 | All results stored in `JOBS["results"]` list forever | ~50 MB held in RAM until server restarts |

---

## What Was Done — Phase by Phase

### Phase 1 — Drop Pandas → csv stdlib (~120 MB saved)

**Files changed:** `utils.py`, `scraper.py`, `main.py`, `watcher.py`, `requirements.txt`

#### `utils.py`
- `get_subject_cols(df)` — was a DataFrame column scan → now iterates `list[dict]` keys
- `generate_class_report(df, ...)` — was full pandas DataFrame operations (`.str.upper()`, `.sum()`, `.nlargest()`, etc.) → rewritten with pure Python loops, `sum()`, `sorted()`
- Both `import pandas as pd` statements removed

#### `scraper.py`
- Removed `import pandas as pd`
- `scrape_departments()` — removed `pd.DataFrame(dept_results)` → now passes `dept_results` (raw `list[dict]`) directly to `get_subject_cols()` and `generate_class_report()`

#### `main.py`
- Removed `import pandas as pd`
- Added `import csv`
- `download_csv()` — replaced `df.to_csv()` with `csv.DictWriter`. Now collects all keys from result dicts, builds column order manually.

#### `watcher.py`
- Added `import csv`
- `build_csv_bytes()` — replaced `pd.DataFrame(results).to_csv()` with `csv.DictWriter`

#### `requirements.txt`
- Removed `pandas`
- Added `tenacity` (pre-added for Phase 2)

---

### Phase 2 — Increase Timeouts + Tenacity Retries

**Files changed:** `scraper.py`, `telegram.py`

#### `scraper.py`
- Added imports: `retry`, `retry_if_exception_type`, `stop_after_attempt`, `wait_exponential_jitter`, `RetryError` from `tenacity`
- `init_session()` — wrapped with `@retry`: **5 attempts**, exponential jitter **5–120s**, retries on `ClientError` / `TimeoutError`. Timeout: **15s → 300s**
- `fetch_one()` — inner `_attempt()` helper retries **3 times** (jitter 2–30s) on network/timeout errors. Timeout: **20s → 300s**. Non-200 HTTP raises `ClientResponseError` so tenacity retries it. `"Not Found / Invalid"` returns immediately — **never retried**.

#### `telegram.py`
- `send_message()` timeout: **20s → 30s**
- `send_document()` timeout: **30s → 60s**

**Key design:** `fetch_one()` is still non-raising — all errors end up as `{"Roll No": ..., "Status": "Error"}` dicts. The retry logic is entirely internal.

---

### Phase 3 — CSRF Token Auto-Refresh

**Files changed:** `scraper.py`, `watcher.py`

#### `scraper.py`
- `fetch_one()` signature changed: `token: str` → `token_holder: dict` where `token_holder = {"token": str, "lock": asyncio.Lock()}`
- New inner `_do_request()` function reads `token_holder["token"]` fresh on every attempt
- **HTTP 419 detection:** acquires lock → calls `init_session()` to get fresh token → raises `ClientResponseError(419)` → tenacity retries with new token
- **JSON token-failure detection:** checks `message`/`error` fields for keywords `"token"`, `"csrf"`, `"unauthenticated"` → same refresh path
- **Double-refresh guard:** `if token_holder["token"] == token` — only the first coroutine through the lock actually calls `init_session()`; the rest just read the already-refreshed value
- `scrape_departments()` — creates `token_holder` after initial `init_session()`, passes it into every `fetch_one()` task

#### `watcher.py`
- Sentinel probe call in `run_watcher_loop()` updated to pass `token_holder` dict instead of bare `token`

---

### Phase 4 — Reduce Watcher Concurrency + Retry SSE Events

**Files changed:** `models.py`, `scraper.py`, `main.py`, `watcher.py`

#### `models.py`
- `FetchRequest.workers` default: **50 → 15**

#### `watcher.py`
- `run_batch_fetch()` hardcoded `workers=50` → **`workers=10`**

#### `scraper.py`
- `fetch_one()` — added optional `retry_callback(roll, attempt)` parameter
- Added `_before_sleep()` sync hook wired to tenacity's `before_sleep=` — fires `asyncio.ensure_future(retry_callback(roll, attempt))` before each retry wait
- `scrape_departments()` — added `retry_callback=None` parameter, threads it through to all `fetch_one()` tasks

#### `main.py`
- `run_scrape_job()` — added `retry_callback` async closure that pushes `{"type": "retry", "roll": ..., "attempt": ..., "message": "Server slow, retrying roll X..."}` to the SSE queue

#### `watcher.py`
- `run_batch_fetch()` — same `retry_callback` defined and passed to `scrape_departments()`

---

### Phase 5 — Stream Results to Temp File (~50 MB saved)

**Files changed:** `main.py`, `watcher.py`, `telegram.py`

#### The Core Idea
Instead of `JOBS["results"] = [row1, row2, ...]` (a growing Python list in RAM), each result is written as a **JSON line** to a temp `.jsonl` file on disk immediately. JOBS only stores the file path string.

#### `main.py`
- Added `import tempfile`
- JOBS schema: `"results": []` → `"results_file": None` (stores temp file path)
- `run_scrape_job()`:
  - Opens `NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)` at job start
  - Stores path in `job["results_file"]`
  - `progress_callback` writes `json.dumps({**result, "Department": dept_name}) + "\n"` and flushes per row
  - `tmp.close()` in `finally` block
- `download_csv()`:
  - Reads `results_file` path from JOBS
  - Opens file, reads line-by-line, `json.loads()` each line into a list
  - Rest of CSV building is identical

#### `watcher.py`
- Added `import tempfile`
- `build_csv_bytes(results_or_path, reports)` — now accepts either a **file path string** (reads jsonl) or a **list** (backward compat)
- `run_batch_fetch()`:
  - Creates `NamedTemporaryFile` at start
  - JOBS gets `"results_file"` instead of `"results": []`
  - `progress_callback` writes jsonl lines and flushes
  - `tmp.close()` in `finally`

#### `telegram.py`
- `send_results_notification()` — prefers `job["results_file"]` (path) over `job["results"]` (list) when calling `build_csv_bytes()`

---

## Projected RAM After All Phases

```
BEFORE:
  Base Python + FastAPI + pandas + aiohttp + bs4  ≈ 160 MB
  10,000 results in JOBS["results"] list          ≈  50 MB
  Peak during scrape                              ≈ 260–345 MB

AFTER (Phases 1–5):
  Base Python + FastAPI + aiohttp + bs4 + tenacity ≈  50 MB
  JOBS["results_file"] = just a file path           ≈   0 MB
  Peak during scrape (dept_results in scraper)      ≈  5–10 MB
  TOTAL PEAK                                        ≈ 60–80 MB
```

---

## Final `requirements.txt`

```
fastapi
uvicorn[standard]
aiohttp
beautifulsoup4
lxml
python-multipart
sse-starlette
tenacity
```
(`pandas` removed — saves ~120 MB baseline)

---

## Phase 6 — Smoke Test Checklist (Your Job)

- [ ] `pip install -r requirements.txt` → confirm `tenacity` installs, `pandas` is gone
- [ ] `python -m uvicorn backend.main:app --reload`
- [ ] Run a small batch (5–10 rolls) via the frontend
- [ ] Confirm SSE stream works (results appear live)
- [ ] Confirm CSV download works (correct columns, class report at bottom)
- [ ] Check temp file exists: `dir $env:TEMP\sgbau_*.jsonl`
- [ ] (Optional) Trigger watcher, confirm Telegram message + CSV attachment arrive
- [ ] `git add -A && git commit -m "chore: Phases 1-5 render optimization"` → `git push`
- [ ] Watch Render build log — confirm `pandas` not installed, `tenacity` is
- [ ] Check Render Metrics tab — RAM should stay under 150 MB for large batches

---

## Key Files Changed Summary

| File | Phases | What Changed |
|---|---|---|
| `requirements.txt` | 1, 2 | Removed `pandas`, added `tenacity` |
| `backend/utils.py` | 1 | `get_subject_cols()` + `generate_class_report()` → pure Python, no pandas |
| `backend/scraper.py` | 1, 2, 3, 4 | No pandas; tenacity retries; token_holder CSRF refresh; retry_callback |
| `backend/main.py` | 1, 4, 5 | No pandas; DictWriter; retry SSE events; temp file streaming |
| `backend/watcher.py` | 1, 4, 5 | No pandas; workers=10; retry_callback; temp file streaming; build_csv_bytes accepts path |
| `backend/telegram.py` | 2, 5 | Bumped timeouts; reads results_file path |
| `backend/models.py` | 4 | Default workers: 50 → 15 |

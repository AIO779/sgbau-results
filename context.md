# SGBAU Results Web App — Project Context

> **Resume file for Antigravity / Cursor / Windsurf.**
> Read this before doing anything else in a new chat.

---

## Spec File

`C:\Users\Atharav\Desktop\DIC\SGBAU_WEBAPP_BUILD_SPEC.md`
— Full 12-phase build specification. Always re-read relevant phase sections before coding.

## Original Script

`C:\Users\Atharav\Desktop\DIC\sgbau_fast_api.py`
— CLI async scraper. Source of truth for scraping logic, parse_result(), generate_roll_range(), and abbreviate().

---

## Project Root

```
C:\Users\Atharav\Desktop\DIC\sgbau-results\
```

---

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Architecture Design (data flow diagram, session safety analysis) | ✅ DONE |
| 2 | Refactor Scraper (`models.py`, `utils.py`, `scraper.py`, `__init__.py`) | ✅ DONE |
| 3 | FastAPI Backend (`main.py` — routes, SSE, CORS, job store, CSV download) | ✅ DONE |
| 4 | Frontend (`index.html`, `style.css`, `app.js`) | ✅ DONE |
| 5 | Local Dev & Testing | ✅ DONE |
| 6 | Config Files (`requirements.txt`, `render.yaml`, `.gitignore`, `README.md`) | ✅ DONE |
| 7 | GitHub Repo + Push | ✅ DONE |
| 8 | Enable GitHub Pages (frontend) | ✅ DONE |
| 9 | Deploy Backend on Render.com | ✅ DONE |
| 10 | Wire Production URLs | ✅ DONE |
| 11 | End-to-End Testing in Production | ⬜ NEXT |
| 12 | Launch & Share | ⬜ TODO |

---

## Current File Tree

```
sgbau-results/
├── backend/
│   ├── __init__.py     ✅ (empty — makes backend a Python package)
│   ├── models.py       ✅ (Pydantic: DeptRequest, FetchRequest, StudentResult, FetchResponse)
│   ├── utils.py        ✅ (generate_roll_range, abbreviate, parse_result)
│   ├── scraper.py      ✅ (init_session, fetch_one, scrape_departments)
│   └── main.py         ✅ (FastAPI app — 4 routes, SSE, CORS, job store, CSV download)
├── docs/
│   ├── index.html      ✅ (single-page app — real SGBAU dropdowns: session/semester/result-type/course)
│   ├── style.css       ✅ (dark-mode, select-wrap custom dropdowns, card-hint, dept-field-course wide)
│   └── app.js          ✅ (81-course catalog, PRESETS auto-fill, SSE, filter/pill, CSV download)
├── requirements.txt    ✅ (fastapi, uvicorn, aiohttp, bs4, lxml, pandas, sse-starlette)
├── render.yaml         ✅ (free-tier web service, pip build, uvicorn start, ALLOWED_ORIGIN env)
├── .gitignore          ✅ (pycache, venvs, results_*/, *.csv, logs, DS_Store)
├── README.md           ✅ (features, stack, local dev, deployment, CSV columns)
└── context.md          ✅ (this file — resume tracker)
```

---

## Phase 2 — Key Implementation Notes

- `sys.exit()` replaced with `raise ValueError(...)` in `generate_roll_range()` (web-safe).
- All scraper config (`session_val`, `course_type`, `result_type`, `sem_code`) passed as **function parameters** — no module-level mutable globals.
- `progress_callback(dept_name, result_dict)` is an **async callable** injected by `main.py`; it puts events onto the SSE queue.
- `scraper.py` imports from `backend.utils` — must always run uvicorn from the **repo root**, not from inside `backend/`.

---

## Phase 3 — Implementation Notes (DONE)

`backend/main.py` contains:

1. **`POST /api/fetch-results`** → `202 FetchResponse` with `job_id` + `total_rolls`.
2. **`GET /api/progress/{job_id}`** → SSE via `EventSourceResponse`; 60 s timeout guard.
3. **`GET /api/download/{job_id}`** → `pandas` DataFrame → `StreamingResponse` CSV.
4. **`GET /api/health`** → `{"status": "ok"}` (also used by UptimeRobot keep-alive).
5. **CORS** via `os.getenv("ALLOWED_ORIGIN", "*")`.
6. **`run_scrape_job()`** background task with `progress_callback` → queue → SSE.

`_count_rolls()` helper strips alpha prefix for approximate progress percentage.

---

## Phase 4 — What To Build Next

Create three files in `docs/`:

### `docs/index.html`
- Header with app title
- **Session settings card**: `session`, `sem_code`, `workers` inputs
- **Departments card**: dynamic dept rows (name, start_roll, end_roll, course_cd) + "+ Add department" button
- **Fetch results** primary button
- **Progress card** (hidden until fetch): label + animated progress bar
- **Results card** (hidden until first SSE event): table (Dept / Roll No / Name / Result / SGPA / Status) + "Download CSV" button
- **Summary card** (hidden until `done` event): grid of per-dept pass/fail stats

### `docs/style.css`
- Premium dark/light design (NOT the plain spec CSS — make it visually stunning)
- CSS variables for colors, radius, transitions
- Responsive flex/grid layouts
- Badge classes: `.badge.pass`, `.badge.fail`, `.badge.atkt`, `.badge.other`
- `.hidden { display: none !important; }`

### `docs/app.js` (DONE)
- `allRows[]` cache + `rebuildTable()` for client-side filter & pill changes
- `setPillFilter(val)` → filters table by PASS/FAIL/ATKT without re-fetching
- `filterTable()` → text search across name + roll columns
- Fetch button disabled while job is running; re-enabled on done/error
- Cold-start warning in progress label

---

## Phase 4 — Implementation Notes (DONE)

**Extra features added beyond spec:**
- Client-side filter bar (text + PASS/FAIL/ATKT pills) — no re-fetch needed
- `allRows[]` cache so filter rebuilds table instantly from memory
- Row fade-in animation (`@keyframes fadeRow`)
- Summary cards with animated pass-rate mini bar
- Fetch button disabled while streaming; re-enabled on completion
- Cold-start warning message in progress label
- Roll numbers styled with `<code>` in indigo for quick scanning

---

## Phase 5 — What To Do Next (Local Dev & Testing)

> **This phase requires manual steps — no code to write.**

1. **Install Python deps** from `sgbau-results/` root:
   ```
   pip install fastapi "uvicorn[standard]" aiohttp beautifulsoup4 lxml pandas python-multipart sse-starlette
   ```
2. **Run the backend** from the repo root (not inside `backend/`):
   ```
   uvicorn backend.main:app --reload --port 8000
   ```
3. **Open the frontend**: open `docs/index.html` in a browser (works as a local file since `API_URL` points to `localhost:8000`).
4. **Test checklist** (DevTools → Network → filter EventSource/Fetch):
   - POST `/api/fetch-results` returns `202` with `job_id`
   - EventSource opens to `/api/progress/{job_id}`
   - Progress bar increments, rows appear
   - `done` event fires, summary renders
   - "Download CSV" produces a valid `.csv`
5. **Common errors** — see spec Phase 5.5 table.

After Phase 5 passes, move to **Phase 6** (config files).

---

## Environment Variables (set on Render.com dashboard)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ALLOWED_ORIGIN` | `*` | CORS origin (set to GitHub Pages URL in prod) |
| `DEFAULT_SESSION` | `SE23` | Default session code |
| `DEFAULT_SEM` | `SM03` | Default semester code |

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI + Python 3.11 + aiohttp |
| Frontend | Vanilla HTML + CSS + JS (no build step) |
| Backend hosting | Render.com (free tier) — auto-deploy from GitHub |
| Frontend hosting | GitHub Pages — served from `/docs` folder |
| Real-time progress | Server-Sent Events (SSE) via `sse-starlette` |

---

## How to Resume

1. Read this file (`context.md`).
2. Find the first `⬜ NEXT` phase in the table above.
3. Read the corresponding phase section in `SGBAU_WEBAPP_BUILD_SPEC.md`.
4. Implement that phase only. Update the status table here when done.
5. Stop and wait for user confirmation before moving to the next phase.

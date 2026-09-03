# SGBAU Results Scraper & Watcher: Comprehensive Architecture Documentation

## 1. Project Overview & Motivation
The **SGBAU Results Scraper & Watcher** is a full-stack, automated platform designed to interface with the Sant Gadge Baba Amravati University (SGBAU) result portal. 

Historically, checking results on the SGBAU portal required manual data entry for every single student, making department-wide analysis incredibly tedious. This project solves that bottleneck by providing:

1. **Manual Batch Fetching (The Scraper)**: A frontend dashboard where administrators can input roll number ranges for multiple departments simultaneously. The backend rapidly fetches all results in parallel, aggregates them, and provides a formatted CSV file complete with a statistical "Class Report".
2. **Automated Result Watcher (The Automation)**: A background service that runs 24/7. An administrator provides a "Sentinel Roll Number" (a single roll number from an expected upcoming result). The server periodically probes the SGBAU endpoint for this specific number. Once the result is successfully fetched (indicating the university has officially published the results), the system automatically executes a full batch scrape and delivers the final CSV report directly to the administrator's Telegram.

### Relevant SGBAU Endpoints
The project interacts directly with the UCanApply portal used by SGBAU:
*   **Result Portal Homepage**: `https://sgbau.ucanapply.com/result-details` (Used to scrape the initial `_token` / CSRF token required for API requests).
*   **Internal API Endpoint**: `https://sgbau.ucanapply.com/get-result-details` (The POST endpoint that returns raw HTML containing a student's result data).

---

## 2. Technology Stack & Infrastructure

The philosophy behind this stack is **high performance, low dependency overhead, and zero-cost hosting capability**.

### Backend Stack
*   **Language**: Python 3.10+
*   **Web Framework**: FastAPI (Chosen for its native `asyncio` support and high throughput).
*   **Server**: Uvicorn (ASGI web server).
*   **Scraping Engine**: `aiohttp` (for asynchronous, non-blocking HTTP requests), `BeautifulSoup4` & `lxml` (for parsing the messy HTML returned by the university API).
*   **Data Processing**: `pandas` (for structuring the scraped data into DataFrames and exporting to CSV).
*   **Real-time Streaming**: `sse-starlette` (Provides Server-Sent Events to push live progress to the frontend).
*   **Notifications**: Python standard libraries (`urllib.request`, `urllib.parse`, `email.policy`, `uuid`) to construct raw `multipart/form-data` payloads for the Telegram Bot API, avoiding bloated third-party wrappers.

### Frontend Stack
*   **Architecture**: Vanilla HTML5, CSS3, and JavaScript (ES6). No frontend frameworks (React/Vue) were used to keep the bundle size negligible and loading times instantaneous.
*   **Styling**: Custom CSS variables, dark-mode first design, glassmorphism UI elements, and responsive CSS Grid/Flexbox layouts.
*   **Communication**: Native `fetch()` API and `EventSource` for consuming SSE streams.

### Deployment & Infrastructure
*   **Backend Hosting**: Render.com (Free Tier Web Service).
*   **Frontend Hosting**: GitHub Pages (Static hosting).
*   **State Persistence**: Render's free tier spins down after inactivity and restarts on new requests. To allow the "Watcher" to survive these ephemeral container restarts, state is persisted to a local JSON file (`watcher_state.json`). A lifespan hook in FastAPI reads this file on boot and resurrects the background polling loop.

---

## 3. Deep Dive: Core Modules & Architecture

### 3.1 `main.py` (The API Gateway & Orchestrator)
This is the entry point of the FastAPI application.
*   **Lifespan Hook (`@asynccontextmanager`)**: 
    *   On server startup, it checks for the existence of `watcher_state.json`.
    *   If the state is `WAITING` or `FETCHING`, it means a watcher was running but the server restarted (e.g., Render spun down the dyno). It automatically re-instantiates the `asyncio.Queue` and restarts `run_watcher_loop`.
*   **Endpoints**:
    *   `POST /api/fetch-results`: Accepts the batch scrape configuration, generates a unique `job_id`, spawns `run_scrape_job` as a background task, and returns `202 Accepted`.
    *   `GET /api/progress/{job_id}`: The SSE endpoint. Yields real-time JSON events (`type: result`, `type: fetching`, `type: done`) to the frontend.
    *   `GET /api/download/{job_id}`: Constructs the final Pandas DataFrame, appends the Class Report text, and streams it back as a `.csv` file download.
    *   `POST /api/watch/start` & `POST /api/watch/verify-pin`: Secure, PIN-protected routes for managing the automated watcher.

### 3.2 `scraper.py` (The Async Extraction Engine)
The scraping logic is completely decoupled from the API logic. It is a pure async function with no global state mutations.
*   **Session Initialization (`init_session`)**: Sends a GET request to the SGBAU Result Portal Homepage. Parses the HTML to extract the `_token` (CSRF token) from either the `<meta>` tags or hidden `<input>` fields.
*   **Concurrency Control**: Uses an `aiohttp.TCPConnector(limit=workers)` and an `asyncio.Semaphore(workers)`. This restricts the maximum number of concurrent outbound connections (typically 15-20) to prevent the SGBAU servers from rate-limiting or IP-banning the Render server.
*   **Data Fetching (`fetch_one`)**: Constructs the exact `x-www-form-urlencoded` payload expected by the SGBAU API (including `COURSETYPE`, `COURSECD`, `RESULTTYPE`, `SESSION`, and the `_token`).
*   **Streaming Callback**: As soon as a single roll number is fetched and parsed, `progress_callback` is awaited, which immediately drops the result into the SSE queue for real-time frontend updates.

### 3.3 `utils.py` (Parsing & Data Normalization)
SGBAU does not return clean JSON; it returns raw HTML tables.
*   **`parse_result()`**: Uses BeautifulSoup to target specific HTML tables. It extracts:
    *   Student Name, Roll Number, and PRN.
    *   Overall SGPA and Result Status (PASS/FAIL/ATKT).
    *   Subject-level grades (handling edge cases where headers like "THEORY" or "PRACTICAL" bleed into the data).
*   **`generate_class_report()`**: Analyzes the Pandas DataFrame to calculate:
    *   Total students, Total Passed, Total Failed.
    *   Passing percentage (`(passed / total) * 100`).
    *   Formats this into a human-readable text block that is appended to the bottom of the CSV file.

### 3.4 `watcher.py` & `watcher_loop.py` (The Automation Engine)
This subsystem allows the server to monitor for undeclared results.
*   **`watcher_state.json`**: A persistent file tracking the `watcher_id`, configuration payload, `probe_count`, and `status`.
*   **`run_watcher_loop()`**: 
    1. Reads the `interval_minutes` from the configuration.
    2. Enters an infinite `while` loop.
    3. Calls `scraper.fetch_one()` for the single **Sentinel Roll Number**.
    4. If the response status is "Not Found / Invalid", it logs the attempt, sleeps for the interval duration, and repeats.
    5. If the response contains actual student data, it breaks the loop.
    6. It then calls `run_batch_fetch()` to scrape the entire configured range.
    7. Finally, it invokes `send_results_notification()` to email/message the admin.

### 3.5 `telegram.py` (The Delivery System)
Handles all communication with the Telegram Bot API (`https://api.telegram.org/bot<TOKEN>/...`).
*   **Zero Dependencies**: Relies entirely on Python's `urllib` to minimize attack surface and dependency weight.
*   **`send_message()`**: Formats text using `MarkdownV2`, escaping required characters, and posts it to the `sendMessage` endpoint.
*   **`send_document()`**: A highly technical implementation of a `multipart/form-data` payload builder. Because Python's `email.mime` module can corrupt binary payloads (like Pandas-generated CSVs containing `\r\n` line endings), this function manually constructs the boundary strings, content-dispositions, and byte concatenations exactly as `curl` would, ensuring the CSV file is delivered uncorrupted.

---

## 6. Frontend Architecture & UI/UX

The frontend is broken into two distinct interfaces, sharing common CSS but maintaining strict separation of concerns.

### 6.1 The Main Dashboard (`index.html` & `app.js`)
*   **Dynamic Form Generation**: Users can add multiple "Department" rows. Each row allows selecting a specific course (e.g., "B.E. Computer Science").
*   **Auto-Prefill Logic**: When a course is selected, `app.js` cross-references a catalog dictionary (`W_PRESETS`) and automatically fills in the expected Roll Number prefix (e.g., `25BD310`), allowing the user to simply type the last two digits.
*   **SSE Consumer**: Uses the browser's native `EventSource` to listen to `/api/progress/{job_id}`.
*   **Live DOM Updates**: As events stream in, the JavaScript dynamically constructs table rows (`<tr>`) and updates a pulsing progress bar. It uses a custom color-coding system (Green for PASS, Red for FAIL, Orange for ATKT).

### 6.2 The Admin Watcher UI (`watcher.html` & `watcher.js`)
*   **Security layer**: The entire UI is wrapped in a `<div id="pin-overlay">` applying a CSS `backdrop-filter: blur()`. A `fetch` request is sent to `/api/watch/verify-pin` containing the user's input. The backend performs a constant-time HMAC comparison against the environment variable `WATCHER_PIN`. If successful, the UI fades in.
*   **Activity Console**: Features a dark-themed, monospace "terminal" that logs every background action the server takes (e.g., `Probe #4: Not declared yet...`).
*   **State Recovery**: If the admin closes the tab and returns hours later, `initPage()` queries `/api/watch/current`. If a watcher is active in the backend, the UI immediately syncs its progress bars, log console, and status badges to the server's current state.

---

## 7. Complete Data Flow (The "Happy Path" Watcher Lifecycle)

1.  **Configuration**: Admin enters `watcher.html`, unlocks with PIN, sets Course (e.g., CSE), Roll Range (`25BD310501` to `25BD310560`), Sentinel (`25BD310501`), and Interval (`10 mins`). Clicks **Start**.
2.  **API Registration**: Request hits `POST /api/watch/start`. `main.py` assigns a UUID, writes to `watcher_state.json`, and spawns `run_watcher_loop` in the background. Responds `202 Accepted`.
3.  **SSE Connection**: `watcher.js` opens an `EventSource` to `/api/watch/status/{uuid}`.
4.  **Probing Phase**: 
    *   Loop wakes up.
    *   Scrapes SGBAU for `25BD310501`.
    *   Receives "Invalid".
    *   Pushes `{"type": "probe", "message": "Not declared yet"}` to the SSE queue.
    *   Sleeps 10 minutes.
5.  **Detection Phase**:
    *   Loop wakes up.
    *   Scrapes SGBAU for `25BD310501`.
    *   Receives valid student data (SGPA: 8.5, PASS).
    *   Loop breaks out of the polling cycle.
6.  **Batch Fetch Phase**: 
    *   Backend automatically creates a standard scrape job for the entire `501`-`560` range.
    *   `scraper.py` fetches all 60 results concurrently.
    *   Results stream to the frontend via SSE.
7.  **Data Processing & Delivery Phase**:
    *   The scraped results are converted to a Pandas DataFrame.
    *   The Class Report is calculated.
    *   `telegram.py` sends a Markdown message: *"🎉 Results Found for CSE! 85% Passed."*
    *   `telegram.py` converts the DataFrame to CSV bytes in-memory and attaches it as a document to the Telegram chat.
8.  **Completion**: State is updated to `DONE`. The browser enables the "Download CSV" button for local saving.

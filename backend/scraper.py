"""
scraper.py — Pure async scraper.
Zero side effects: no CLI, no file I/O, no mutable globals.
All configuration is passed in as function parameters.
"""

import asyncio
import aiohttp
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    RetryError,
)
from backend.utils import (
    generate_roll_range,
    parse_result,
    get_subject_cols,
    generate_class_report,
)

URL_MAIN = "https://sgbau.ucanapply.com/result-details"
URL_API  = "https://sgbau.ucanapply.com/get-result-details"

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@retry(
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=5, max=120, jitter=10),
    reraise=True,
)
async def init_session(http: aiohttp.ClientSession) -> str | None:
    """
    Fetch the CSRF token from the SGBAU result page.
    Returns None if the page loads but contains no token.
    Retries up to 5 times (exponential backoff + jitter, 5–120 s) on
    network/timeout errors — mirrors the plan's §2 retry spec.
    """
    async with http.get(URL_MAIN, timeout=aiohttp.ClientTimeout(total=300)) as resp:
        from bs4 import BeautifulSoup
        html = await resp.text()
        soup = BeautifulSoup(html, "lxml")

        token = soup.find("meta", attrs={"name": "csrf-token"})
        if token:
            return token.get("content")

        token = soup.find("input", attrs={"name": "_token"})
        if token:
            return token.get("value")

    return None


async def fetch_one(
    http:          aiohttp.ClientSession,
    token_holder:  dict,             # {"token": str, "lock": asyncio.Lock()}
    roll:          str,
    semaphore:     asyncio.Semaphore,
    course_cd:     str,
    session_val:   str,
    course_type:   str,
    result_type:   str,
    sem_code:      str,
    retry_callback = None,           # async callable: (roll: str, attempt: int) -> None
) -> dict:
    """
    Fetch result for a single roll number.
    Returns a result dict with at minimum: Roll No, Status.
    Never raises — errors are captured inside the dict.

    Token auto-refresh (Phase 3):
      If the server returns HTTP 419 or a JSON body that indicates a stale
      CSRF token, one coroutine acquires token_holder["lock"] and calls
      init_session() to refresh; all others wait, then read the new token.

    Tenacity retries (Phase 2):
      Up to 3 attempts on transient network / timeout errors.
      "Not Found / Invalid" is a valid API response and is never retried.

    Retry SSE events (Phase 4):
      If retry_callback is provided, it is called before each sleep with
      the roll number and current attempt number so the SSE stream can
      push a {"type": "retry"} event to the browser.
    """

    async def _do_request() -> dict:
        """One HTTP attempt, using whatever token is current in token_holder."""
        token = token_holder["token"]
        payload = {
            "_token":     token,
            "session":    session_val,
            "COURSETYPE": course_type,
            "COURSECD":   course_cd,
            "RESULTTYPE": result_type,
            "p1":         "",
            "ROLLNO":     roll,
            "SEMCODE":    sem_code,
            "all":        "",
        }
        req_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-TOKEN":     token,
            "Referer":          URL_MAIN,
        }
        async with http.post(
            URL_API,
            data=payload,
            headers=req_headers,
            timeout=aiohttp.ClientTimeout(total=300),
        ) as res:
            # ── Token expired — refresh and signal caller to retry ────────────
            if res.status == 419:
                async with token_holder["lock"]:
                    # Only refresh if nobody else already did
                    if token_holder["token"] == token:
                        new_token = await init_session(http)
                        if new_token:
                            token_holder["token"] = new_token
                # Signal tenacity to retry (with the fresh token)
                raise aiohttp.ClientResponseError(
                    request_info=res.request_info,
                    history=(),
                    status=419,
                    message="CSRF token expired — refreshed, retrying",
                )

            if res.status == 200:
                data = await res.json()

                # Some SGBAU responses return status=false with a token-error message
                if not data.get("status"):
                    msg = str(data.get("message", "") or data.get("error", "")).lower()
                    if "token" in msg or "csrf" in msg or "unauthenticated" in msg:
                        async with token_holder["lock"]:
                            if token_holder["token"] == token:
                                new_token = await init_session(http)
                                if new_token:
                                    token_holder["token"] = new_token
                        raise aiohttp.ClientResponseError(
                            request_info=res.request_info,
                            history=(),
                            status=419,
                            message="CSRF token invalid (detected via JSON) — refreshed",
                        )
                    # Normal "no result found" response — not an error
                    return {"Roll No": roll, "Status": "Not Found / Invalid"}

                return parse_result(data.get("html", ""), roll)

            # Other non-200 — treat as transient, let tenacity retry
            raise aiohttp.ClientResponseError(
                request_info=res.request_info,
                history=(),
                status=res.status,
                message=f"HTTP {res.status}",
            )

    # ── Phase 4: before_sleep hook — fires an SSE retry event before each wait ──
    def _before_sleep(retry_state) -> None:
        if retry_callback is not None:
            attempt = retry_state.attempt_number
            asyncio.ensure_future(retry_callback(roll, attempt))

    @retry(
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30, jitter=5),
        before_sleep=_before_sleep,
        reraise=True,
    )
    async def _attempt() -> dict:
        return await _do_request()

    async with semaphore:
        try:
            return await _attempt()
        except (RetryError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return {"Roll No": roll, "Status": "Error", "Error": str(exc)}
        except Exception as exc:
            return {"Roll No": roll, "Status": "Error", "Error": str(exc)}


async def scrape_departments(
    departments,        # list of DeptRequest (Pydantic) objects
    session_val:  str,
    course_type:  str,
    result_type:  str,
    sem_code:     str,
    workers:      int,
    progress_callback,  # async callable: (dept_name: str, result: dict) -> None
    retry_callback=None,  # async callable: (roll: str, attempt: int) -> None  (Phase 4)
) -> list:
    """
    Master async runner.

    Creates one aiohttp session + one CSRF token (held in a mutable
    token_holder so Phase-3 auto-refresh can update it mid-run), then
    scrapes all departments sequentially (each department's roll numbers
    are fetched concurrently up to `workers` connections).

    Calls progress_callback(dept_name, result_dict) after every single
    result so the SSE stream can push it to the browser in real-time.

    Calls retry_callback(roll, attempt) before each tenacity sleep so the
    SSE stream can push a {"type": "retry"} event (Phase 4).

    Returns a list of per-department summary dicts:
        { name, range, results, total, passed }
    """
    connector = aiohttp.TCPConnector(limit=workers)
    async with aiohttp.ClientSession(headers=UA_HEADERS, connector=connector) as http:

        token = await init_session(http)
        if not token:
            raise RuntimeError(
                "Failed to fetch CSRF token from SGBAU site. "
                "The site may be down or its HTML structure has changed."
            )

        # Phase 3: shared mutable token holder passed into every fetch_one()
        token_holder: dict = {
            "token": token,
            "lock":  asyncio.Lock(),
        }

        summaries = []

        for dept in departments:
            rolls     = generate_roll_range(dept.start_roll, dept.end_roll)
            semaphore = asyncio.Semaphore(workers)

            tasks = [
                asyncio.create_task(
                    fetch_one(
                        http, token_holder, roll, semaphore,
                        dept.course_cd, session_val,
                        course_type, result_type, sem_code,
                        retry_callback=retry_callback,   # Phase 4
                    )
                )
                for roll in rolls
            ]

            dept_results = []
            for future in asyncio.as_completed(tasks):
                result = await future
                dept_results.append(result)
                await progress_callback(dept.name, result)   # stream to SSE

            # ── Build report from this department's raw results list ────────────
            subj_cols  = get_subject_cols(dept_results) if dept_results else []
            class_rpt  = generate_class_report(dept_results, subj_cols, dept.name)

            summaries.append({
                "name":         dept.name,
                "range":        f"{dept.start_roll} → {dept.end_roll}",
                "results":      dept_results,
                "total":        class_rpt["total_students"],
                "passed":       class_rpt["passed"],
                "class_report": class_rpt,          # ← structured dict for frontend
            })

        # Allow underlying transports to close gracefully on Windows
        await asyncio.sleep(0.25)

    return summaries

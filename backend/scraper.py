"""
scraper.py — Pure async scraper.
Zero side effects: no CLI, no file I/O, no mutable globals.
All configuration is passed in as function parameters.
"""

import asyncio
import aiohttp
from backend.utils import generate_roll_range, parse_result

URL_MAIN = "https://sgbau.ucanapply.com/result-details"
URL_API  = "https://sgbau.ucanapply.com/get-result-details"

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


async def init_session(http: aiohttp.ClientSession) -> str | None:
    """Fetch the CSRF token from the SGBAU result page. Returns None on failure."""
    try:
        async with http.get(URL_MAIN, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            from bs4 import BeautifulSoup
            html = await resp.text()
            soup = BeautifulSoup(html, "lxml")

            token = soup.find("meta", attrs={"name": "csrf-token"})
            if token:
                return token.get("content")

            token = soup.find("input", attrs={"name": "_token"})
            if token:
                return token.get("value")
    except Exception:
        pass
    return None


async def fetch_one(
    http:        aiohttp.ClientSession,
    token:       str,
    roll:        str,
    semaphore:   asyncio.Semaphore,
    course_cd:   str,
    session_val: str,
    course_type: str,
    result_type: str,
    sem_code:    str,
) -> dict:
    """
    Fetch result for a single roll number.
    Returns a result dict with at minimum: Roll No, Status.
    Never raises — errors are captured inside the dict.
    """
    async with semaphore:
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
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-TOKEN":     token,
            "Referer":          URL_MAIN,
        }
        try:
            async with http.post(
                URL_API,
                data=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as res:
                if res.status == 200:
                    data = await res.json()
                    if data.get("status"):
                        return parse_result(data.get("html", ""), roll)
                    else:
                        return {"Roll No": roll, "Status": "Not Found / Invalid"}
                else:
                    return {"Roll No": roll, "Status": f"HTTP {res.status}"}
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
) -> list:
    """
    Master async runner.

    Creates one aiohttp session + one CSRF token, then scrapes all
    departments sequentially (each department's roll numbers are fetched
    concurrently up to `workers` connections).

    Calls progress_callback(dept_name, result_dict) after every single
    result so the SSE stream can push it to the browser in real-time.

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

        summaries = []

        for dept in departments:
            rolls     = generate_roll_range(dept.start_roll, dept.end_roll)
            semaphore = asyncio.Semaphore(workers)

            tasks = [
                asyncio.create_task(
                    fetch_one(
                        http, token, roll, semaphore,
                        dept.course_cd, session_val,
                        course_type, result_type, sem_code,
                    )
                )
                for roll in rolls
            ]

            dept_results = []
            for future in asyncio.as_completed(tasks):
                result = await future
                dept_results.append(result)
                await progress_callback(dept.name, result)   # stream to SSE

            summaries.append({
                "name":    dept.name,
                "range":   f"{dept.start_roll} → {dept.end_roll}",
                "results": dept_results,
                "total":   len([r for r in dept_results if r.get("Status") == "OK"]),
                "passed":  len([
                    r for r in dept_results
                    if r.get("Status") == "OK"
                    and str(r.get("Result", "")).upper() == "PASS"
                ]),
            })

        # Allow underlying transports to close gracefully on Windows
        await asyncio.sleep(0.25)

    return summaries

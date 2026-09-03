# SGBAU Results App - Personalized Learning Roadmap

**Time Commitment:** 4-6 hours per week (broken down into 3 manageable days per week)
**Goal:** Deeply understand the architecture, be able to confidently explain it to others, and learn how to build similar real-time web applications.

---

## Week 1: Getting Through the Front Door (Scraper Basics)
*Focus: Understanding how your code tricks the university server and parses the messy data that comes back.*

### Day 1: HTTP Requests & CSRF Tokens
- **Theory (1 hr):** SGBAU protects its results from bots. If you just ask for a result, it denies you. You need a "ticket" (a CSRF token) to pretend you are a human using a browser.
- **Code Walkthrough (30 mins):** Read `backend/scraper.py`, specifically the `init_session()` function. See where it secretly reads the `<meta name="csrf-token">` tag to grab the ticket.
- **Exercise (30 mins):** Inside `init_session` in `backend/scraper.py`, add `print("My stolen token is:", token)` right before returning the token. Run the scraper locally and see the actual token printed in your terminal!

### Day 2: HTML Parsing with BeautifulSoup
- **Theory (1 hr):** The university doesn't send you a clean spreadsheet; it sends messy HTML code. We use BeautifulSoup to extract the exact text (names, grades, etc.).
- **Code Walkthrough (30 mins):** Open `backend/utils.py` and read the `parse_result()` function. Notice how it hunts for `<tr>` (table row) and `<td>` tags to pull out data.
- **Exercise (30 mins):** Add `print(f"I found a student named: {record.get('Name')}")` near the bottom of `parse_result()`. Watch your terminal light up with decoded names as they are scraped.

### Day 3: Week 1 Review & Experimentation
- **Task (1.5 hrs):** Trace the path of a single roll number. Open `backend/scraper.py` and read through `fetch_one()`. See how it uses the token from Day 1, sends a POST request, and passes the HTML to the function you studied on Day 2.

---

## Week 2: Need for Speed (Async Python)
*Focus: Understanding how your app achieves its incredible speed compared to checking results manually.*

### Day 4: The `asyncio` Loop
- **Theory (1 hr):** Normal Python waits for one page to load before moving to the next. `asyncio` fires off 50 requests at once and deals with the responses whenever they arrive.
- **Code Walkthrough (30 mins):** Look at `scrape_departments()` and the `asyncio.as_completed(tasks)` block in `backend/scraper.py`. This is where all the requests run concurrently.
- **Exercise (30 mins):** Open `backend/models.py` and change the default `workers: int = 50` to `workers: int = 1`. Run a small scrape from your browser and watch how incredibly slow it is. Change it back to 50 when you're done!

### Day 5: Semaphores (The Bouncer)
- **Theory (45 mins):** If you fire 5,000 requests at exactly the same millisecond, SGBAU will block you or crash. A Semaphore acts as a bouncer, strictly limiting active connections to a set limit (e.g., 50).
- **Code Walkthrough (45 mins):** Check how `semaphore = asyncio.Semaphore(workers)` is initialized in `scrape_departments()` and how it's used inside `fetch_one()` with `async with semaphore:`.
- **Exercise (30 mins):** Temporarily set your workers to `150` on the frontend. Observe if the university server starts returning HTTP timeout errors in your terminal. (Keep this brief to be polite to the university servers!)

### Day 6: Week 2 Review & Consolidation
- **Task (1 hr):** Explain out loud to yourself (or a rubber duck) the difference between scraping with 1 worker vs 50 workers. Why do we need the Semaphore?

---

## Week 3: The Brain of the App (FastAPI & Data Handling)
*Focus: Understanding how the server coordinates tasks and crunches the numbers for the frontend.*

### Day 7: FastAPI & Background Tasks
- **Theory (1 hr):** When you click "Fetch Results", the server can't freeze for 2 minutes while it works, or your browser will show a timeout error. It must instantly reply "Started!" and do the heavy lifting in the background.
- **Code Walkthrough (30 mins):** Look at the `fetch_results()` endpoint in `backend/main.py`. Notice the `background_tasks.add_task(...)` line and how it immediately returns a `job_id`.
- **Exercise (45 mins):** Add a brand-new API route in `backend/main.py`. Just above the `health` function, type:
  ```python
  @app.get("/api/hello")
  def say_hello(): 
      return {"message": "Hello from my custom route!"}
  ```
  Run your local server, visit `localhost:8000/api/hello` in your browser, and see your new feature in action.

### Day 8: Data Manipulation with Pandas
- **Theory (1 hr):** After collecting hundreds of results, we need to calculate pass percentages and find the top 5 students. We use Python's Pandas library for this math.
- **Code Walkthrough (30 mins):** Read `generate_class_report()` in `backend/utils.py`. See how it uses `valid['Result'].str.upper() == 'PASS'` to count passing students.
- **Exercise (45 mins):** In `generate_class_report`, temporarily break the logic! Change `report['failed'] = total - passed` to `report['failed'] = total - passed + 500`. Run a fetch and see the hilarious, incorrect percentage on your frontend. Fix it back!

### Day 9: Week 3 Review & Flow Mapping
- **Task (1 hr):** Grab a piece of paper and map the backend data flow: User Request -> `fetch_results()` -> `run_scrape_job()` -> Pandas reporting. 

---

## Week 4: The Live Experience (Frontend-Backend Connection)
*Focus: Connecting your vanilla JS frontend to your Python backend to create a real-time show.*

### Day 10: Server-Sent Events (SSE)
- **Theory (1 hr):** This powers your live progress bar. Instead of the browser repeatedly asking "Are you done yet?", the server keeps a one-way walkie-talkie channel open and shouts "I found a result!" over and over.
- **Code Walkthrough (30 mins):** Check `progress_stream()` in `backend/main.py` (the server shouting) and `openSSE()` in `docs/app.js` (the browser listening via `EventSource`).
- **Exercise (30 mins):** In `docs/app.js` inside `openSSE()`, change the line `setProgress(...)` to include a funny message like `"Hacking SGBAU servers... ${countReceived} files stolen"`. Run the frontend and see it change live.

### Day 11: Vanilla DOM Manipulation (JavaScript)
- **Theory (45 mins):** Your `index.html` file is mostly empty! The `app.js` file reads the data coming from SSE and physically injects HTML tables and reports into the page on the fly.
- **Code Walkthrough (45 mins):** Look at `renderRow()` and `renderClassReports()` in `docs/app.js`. See how backticks (`) are used for template literals to mix HTML with JavaScript variables.
- **Exercise (30 mins):** Inside `renderRow(d)` in `docs/app.js`, look for the line that prints the student's name: `<td>${d.name}</td>`. Change it to `<td><strong>${d.name}</strong></td>` to make every student's name bold.

### Day 12: Architecture Pitch & Final Review
- **Task (2 hrs):** Use this final day to practice explaining your project. Try pitching these 3 core concepts to a non-technical friend:
  1. **Server-Sent Events (SSE):** How you built a live progress dashboard without loading spinners.
  2. **Concurrency (Semaphores):** How you fetch thousands of results so fast without crashing servers.
  3. **CSRF Tokens:** How your code bypasses security to pretend to be a real browser.

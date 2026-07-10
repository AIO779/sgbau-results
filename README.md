# SGBAU Result Checker

A web app that fetches **Sant Gadge Baba Amravati University (SGBAU)** results for multiple departments simultaneously — no Python installation required for end users.

## Live App

| | URL |
|---|---|
| **Frontend** (share this link) | `https://yourusername.github.io/sgbau-results` |
| **API** (called automatically) | `https://sgbau-results-api.onrender.com` |
| **API docs** | `https://sgbau-results-api.onrender.com/docs` |
| **Health check** | `https://sgbau-results-api.onrender.com/api/health` |

> Replace `yourusername` with your actual GitHub username after deployment.

---

## Features

- **Multi-department**: fetch results for CSE, IT, EXTC, etc. in one run
- **Live progress**: server-sent events stream each result to the browser in real time
- **Filter & search**: filter results by name/roll number or by PASS / FAIL / ATKT
- **Clean CSV export**: downloads Roll No, Name, SGPA, College + subject grades — no raw data noise
- **Department summary**: pass rate bar and student count per department

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python 3.11 + aiohttp |
| Frontend | Vanilla HTML + CSS + JS (no build step) |
| Backend hosting | Render.com (free tier) |
| Frontend hosting | GitHub Pages (`/docs` folder) |
| Real-time progress | Server-Sent Events (SSE) |

---

## Local Development

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/sgbau-results.git
cd sgbau-results

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the backend (run from repo root, not from inside backend/)
python -m uvicorn backend.main:app --reload --port 8000

# 4. Open the frontend
# Open docs/index.html in your browser
# API_URL in app.js is already set to http://localhost:8000
```

---

## Parameters

| Code | Example | Meaning |
|---|---|---|
| Session | `SE23` | Winter 2023 session |
| Semester | `SM03` | Third semester |
| Course type | `UG` | Undergraduate |
| Result type | `R` | Regular |

---

## Deployment

### Backend → Render.com
1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → New Web Service → connect this repo.
3. Render auto-detects `render.yaml` and deploys.
4. Set `ALLOWED_ORIGIN` env variable to your GitHub Pages URL.

### Frontend → GitHub Pages
1. Repo Settings → Pages → Source: `main` branch, `/docs` folder.
2. Update `API_URL` in `docs/app.js` to your Render URL before pushing.

---

## Keeping the Backend Awake (Optional)

Render's free tier sleeps after 15 minutes of inactivity.
Use [UptimeRobot](https://uptimerobot.com) (free) to ping `/api/health` every 10 minutes.

---

## CSV Output Columns

`Roll No` | `Name` | `SGPA` | `College` | `<subject abbreviations…>`

Subject columns use abbreviated names from the SGBAU result card (e.g. `AM` = Applied Mathematics, `DS` = Data Structures).

---

*Data sourced from [sgbau.ucanapply.com](https://sgbau.ucanapply.com)*

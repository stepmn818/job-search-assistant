# 🎯 AI Job Search Assistant

A personal AI agent that analyses how well your CV matches a job description — built with Streamlit + Claude API.

**Portfolio project** demonstrating: AI integration, structured prompting, and workflow automation thinking.

---

## Problem Statement

Job hunting is time-consuming and opaque. Most candidates apply to roles without a clear read on how well their CV actually matches the job description — they either apply to everything hoping something sticks, or talk themselves out of roles they're actually qualified for.

Manually comparing a CV to a JD is tedious, subjective, and easy to get wrong. You miss keywords, underestimate transferable experience, or fail to spot the one gap a recruiter will flag immediately.

---

## What This Tool Does

Upload or paste your CV and paste a job description. The tool analyses both and returns:

- **Fit Score** — a calibrated 0–100 score reflecting overall alignment, derived as a weighted rollup of four sub-scores (so the number is never a black box)
- **Sub-Scores** — 0–100 each on Skills (35%), Experience (30%), Domain (25%), and Education (10%), with a one-sentence rationale explaining which dimensions drove the total
- **Top Strengths** — where your experience directly matches what the role needs
- **Skill Gaps** — what's missing or under-evidenced in your CV relative to the JD
- **Quick Wins** — specific, actionable steps to improve your fit right now, whether that's a CV tweak, a certification, or a reframe
- **One-Line Recruiter Summary** — how a recruiter reading your CV would likely position you for this role

From there, save the analysis straight to the **Application Tracker** (a second page in the app's sidebar nav) to log the company, role, and fit score, then track status through Considering → Applied → Interview → Offer/Rejected as your search progresses.

The goal isn't to game the application process. It's to help candidates make smarter decisions about where to focus their energy — and show up better prepared when they do apply.

---

## Built With

| Layer | Technology |
|---|---|
| UI | [Streamlit](https://streamlit.io) |
| AI | [Anthropic Claude API](https://www.anthropic.com) — `claude-haiku-4-5-20251001` |
| Persistence | SQLite (`database.py`), rendered with `pandas` |
| File parsing | `pypdf`, `python-docx` |
| Language | Python 3.14+ |
| Dev tooling | [Claude Code CLI](https://claude.ai/code) |

---

## How to Run

**Prerequisites:** Python 3.14+, an Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

**Recommended — with [uv](https://docs.astral.sh/uv/):**

```bash
# 1. Install dependencies into a managed virtualenv, from the uv.lock lockfile
uv sync

# 2. Add your API key — create a .env file in the project root
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# 3. Start the app
uv run streamlit run CV_Fit_Scorer.py
```

**Without uv, using plain pip:**

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your API key — create a .env file in the project root
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# 3. Start the app
python -m streamlit run CV_Fit_Scorer.py
```

Open [http://localhost:8501](http://localhost:8501)

---

## Project Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | CV vs JD fit scorer | ✅ Done |
| 2 | Application tracker (SQLite) | ✅ Done |
| 3 | CV tailoring engine (auto-rewrite bullets to match JD) | 🔜 Next |
| 4 | Automated job discovery agent (daily digest via email) | 📋 Planned |

---

> Built with [Claude Code](https://claude.ai/code) — the `CLAUDE.md` file in this repo gives Claude full context on project architecture and conventions for easy extension.

# Job Search Assistant — Claude Code Context

## What this project is
An AI-powered job search assistant built with Streamlit + Anthropic Claude API.
- Phase 1: CV vs Job Description fit scorer. Done.
- Phase 2: Application tracker (SQLite backend). Done.
- Phase 3 (planned): CV tailoring engine (auto-rewrite bullets to match JD)
- Phase 4 (planned): Automated job discovery agent (daily digest via email)

## Requirements
- Python 3.14+ (see `pyproject.toml`'s `requires-python`)

## Commands
- `pip install -r requirements.txt` — install dependencies (or `uv sync` — this repo also has a `uv.lock`)
- `python -m streamlit run CV_Fit_Scorer.py` — start the app (runs on http://localhost:8501)
- `pytest tests/` — run the test suite

## Architecture
- `CV_Fit_Scorer.py` — Streamlit UI for the fit scorer (also the entry script; its filename is the sidebar label)
- `pages/Application_Tracker.py` — Streamlit multi-page UI for the application tracker (read-only table + edit form)
- `utils.py` — Claude API calls, prompt logic, JSON parsing
- `database.py` — SQLite persistence for saved applications
- `job_search.db` — SQLite file created at runtime by `database.init_db()`; gitignored, never commit it
- `tests/test_utils.py` — unit tests for utils.py (pytest + unittest.mock)
- `tests/test_database.py` — unit tests for database.py
- `tests/test_cv_fit_scorer.py` — Streamlit `AppTest` tests for the fit scorer page
- `tests/test_application_tracker.py` — Streamlit `AppTest` tests for the tracker page
- `.env` / `.streamlit/secrets.toml` — API key (never commit these)

## Key conventions
- Claude model: always use `claude-haiku-4-5-20251001`
- All Claude API calls live in `utils.py`, never in `CV_Fit_Scorer.py`
- API key loaded from env var `ANTHROPIC_API_KEY`
- Claude responses are structured JSON — parse with `json.loads()` after stripping fences
- Streamlit state: use `st.session_state` for any persistence between reruns
- `utils.py` raises exceptions on error; `CV_Fit_Scorer.py` catches and displays them via `st.error`
- All SQLite writes funnel through `database.update_application()` / `database.insert_application()` — never write to `job_search.db` from a page directly
- Streamlit page tests use `st.testing.v1.AppTest`. Because AppTest re-executes the whole script on every `.run()`, mock Claude calls by patching `utils.analyze_fit` (where it's defined), not `CV_Fit_Scorer.analyze_fit` (a separate, disconnected import) — the latter silently no-ops and lets the real API get called

## Fit score schema
`analyze_fit` returns a structured dict with these fields:
- `fit_score` (0–100) — **derived in Python**, not emitted by the model. Computed inside `analyze_fit` as `round(0.35*skills + 0.30*experience + 0.25*domain + 0.10*education)` from the sub_scores the model returns. Removes both sampling noise on the total and "model did the arithmetic wrong" as a failure mode.
- `sub_scores` — dict with `skills`, `experience`, `domain`, `education` (each 0–100). The model emits these directly.
- `score_rationale` — one sentence naming the 1–2 sub-scores that drove the total.
- `strengths`, `gaps`, `quick_wins` — lists of strings (variable length, no padding).
- `recruiter_summary` — one sentence.

Sub-score weights live in the rollup expression inside `analyze_fit` and are surfaced in the UI labels (e.g. "Skills (35%)"). If you change them, update both places and the README.

## Prompt caching
`analyze_fit` uses two `cache_control: ephemeral` breakpoints:
1. System prompt (scoring rules + JSON schema)
2. CV text (first user content block)

The JD is the only uncached block. When the user compares the same CV against multiple JDs in a session, everything up to and including the CV is served from cache — reducing latency and input token cost on repeat calls.
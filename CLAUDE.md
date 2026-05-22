# Job Search Assistant — Claude Code Context

## What this project is
An AI-powered job search assistant built with Streamlit + Anthropic Claude API.
- Phase 1: CV vs Job Description fit scorer.
- Phase 2 (planned): Application tracker (SQLite backend)
- Phase 3 (planned): CV tailoring engine (auto-rewrite bullets to match JD)
- Phase 4 (planned): Automated job discovery agent (daily digest via email)

## Commands
- `pip install -r requirements.txt` — install dependencies
- `streamlit run app.py` — start the app (runs on http://localhost:8501)
- `pytest tests/` — run the test suite

## Architecture
- `app.py` — Streamlit UI, all page layout and user interaction
- `utils.py` — Claude API calls, prompt logic, JSON parsing
- `tests/test_utils.py` — unit tests for utils.py (pytest + unittest.mock)
- `.env` / `.streamlit/secrets.toml` — API key (never commit these)

## Key conventions
- Claude model: always use `claude-sonnet-4-6`
- All Claude API calls live in `utils.py`, never in `app.py`
- API key loaded from env var `ANTHROPIC_API_KEY`
- Claude responses are structured JSON — parse with `json.loads()` after stripping fences
- Streamlit state: use `st.session_state` for any persistence between reruns
- `utils.py` raises exceptions on error; `app.py` catches and displays them via `st.error`

## Fit score schema
`analyze_fit` returns a structured dict with these fields:
- `fit_score` (0–100) — **derived**, not opinion. Computed as `round(0.35*skills + 0.30*experience + 0.25*domain + 0.10*education)`.
- `sub_scores` — dict with `skills`, `experience`, `domain`, `education` (each 0–100).
- `score_rationale` — one sentence naming the 1–2 sub-scores that drove the total.
- `strengths`, `gaps`, `quick_wins` — lists of strings (variable length, no padding).
- `recruiter_summary` — one sentence.

Sub-score weights are fixed in `_SYSTEM_PROMPT` and surfaced in the UI labels (e.g. "Skills (35%)"). If you change them, update both places and the README.

## Prompt caching
`analyze_fit` uses two `cache_control: ephemeral` breakpoints:
1. System prompt (scoring rules + JSON schema)
2. CV text (first user content block)

The JD is the only uncached block. When the user compares the same CV against multiple JDs in a session, everything up to and including the CV is served from cache — reducing latency and input token cost on repeat calls.
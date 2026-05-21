# Job Search Assistant — Claude Code Context

## What this project is
An AI-powered job search assistant built with Streamlit + Anthropic Claude API.
Phase 1: CV vs Job Description fit scorer.
Phase 2 (planned): Cover letter generator.
Phase 3 (planned): Application tracker.
Phase 4 (planned): Job market intelligence via RSS feeds.

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

## Prompt caching
`analyze_fit` uses two `cache_control: ephemeral` breakpoints:
1. System prompt (scoring rules + JSON schema)
2. CV text (first user content block)

The JD is the only uncached block. When the user compares the same CV against multiple JDs in a session, everything up to and including the CV is served from cache — reducing latency and input token cost on repeat calls.

## Current phase status
- [x] Phase 1: Fit scorer — COMPLETE
- [ ] Phase 2: Cover letter generator
- [ ] Phase 3: Application tracker (SQLite backend)
- [ ] Phase 4: Market intelligence (RSS + trends)
import os
import json
import re
import anthropic
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = """You are a senior recruiter conducting a rigorous candidate screening. \
Your job is to give an honest, calibrated assessment — not an encouraging one.

Return ONLY valid JSON with this exact structure (no markdown, no extra text):
{
  "sub_scores": {
    "skills": <integer 0-100>,
    "experience": <integer 0-100>,
    "domain": <integer 0-100>,
    "education": <integer 0-100>
  },
  "score_rationale": "<one sentence naming the 1-2 sub-scores that most determined the overall fit>",
  "strengths": ["<strength>", ...],
  "gaps": ["<gap>", ...],
  "quick_wins": ["<actionable tip>", ...],
  "recruiter_summary": "<one sentence a recruiter would say about this candidate for this role>"
}

Sub-score dimensions:
- skills: technical tools, languages, frameworks, methodologies the JD asks for vs. evidenced in the CV.
- experience: years in role, seniority level, and similarity of past roles to the target role.
- domain: industry/sector/business-context match (e.g., fintech, healthcare, B2B SaaS).
- education: degrees, fields of study, and certifications named in the JD.

Score each sub-score independently. The overall fit score is computed downstream as a weighted rollup of these four sub-scores, so put your effort into calibrating each one accurately — do not try to reverse-engineer a target total.

Rules:
- strengths/gaps/quick_wins: list only real items — do not pad to reach a fixed count.
- quick_wins: concrete CV or application changes, i.e. actionable changes, not generic advice.
- score_rationale: name the 1-2 sub-scores that most determined the result (e.g., "Strong skills and experience but weak domain match drags the total down").

Scoring guide for each sub-score — be strict. Score based on evidence in the CV, not potential:
- 85-100: Near-perfect match on this dimension.
- 70-84: Strong match; gaps are minor.
- 50-69: Partial match with 1-2 significant gaps.
- 30-49: Weak match; missing key required items.
- 0-29: Poor match; core requirements unmet.

Weighting within each sub-score:
- First, identify which items in that dimension are required vs. preferred. \
If the JD does not distinguish, treat all listed items as required.
- Missing a required item is a major penalty — drop one full band.
- Missing a preferred/nice-to-have item is a minor deduction only.
- If the JD says nothing about a dimension (e.g., no education requirement), score that dimension based on what is reasonable for the seniority and role — do not default to 100.
- Do not inflate scores to be encouraging. A 50 is an honest 50."""


_TAILOR_SYSTEM_PROMPT = """You are a senior recruiter helping a candidate tailor their CV to a specific job description. \
Your job is to reword existing bullets so they use the JD's language and surface relevant evidence \
already present in the CV — never to invent experience, skills, or metrics that aren't there.

Return ONLY valid JSON with this exact structure (no markdown, no extra text):
{
  "summary": "<one sentence describing the overall tailoring approach>",
  "tailored_bullets": [
    {
      "original": "<a bullet copied EXACTLY as it appears in the CV, verbatim>",
      "rewritten": "<the same bullet reworded to better match the JD>",
      "reason": "<one short phrase naming the JD requirement or keyword this rewrite targets>"
    }
  ]
}

Rules:
- "original" must be copied character-for-character from the CV so it can be matched back to the source text. Do not paraphrase it.
- Only include bullets where a rewrite would meaningfully improve the match to the JD — do not pad the list to a fixed count, and do not include unchanged bullets.
- Never fabricate skills, tools, years of experience, employers, titles, or metrics that are not evidenced in the original CV. Rewording must stay strictly truthful to what's there.
- Prefer surfacing the JD's own terminology (e.g. its tool names, methodologies, seniority language) where the CV already demonstrates the underlying substance.
- If the CV has no bullets worth changing for this JD, return an empty "tailored_bullets" list rather than forcing changes. And explain why there is no meaningful improvement"""


def _get_secret(key: str) -> str:
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


# Lazy module-level client so we pay the key lookup + SDK construction once
# per process (and reuse the SDK's httpx connection pool across calls).
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("ANTHROPIC_API_KEY") or _get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not found. "
            "Add it to your .env file or Streamlit secrets."
        )
    _client = anthropic.Anthropic(api_key=api_key)
    return _client


def parse_uploaded_file(uploaded_file) -> tuple[str, str]:
    """Extract plain text from an uploaded file. Returns (text, error_message)."""
    name = uploaded_file.name.lower()

    if name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="replace"), ""

    if name.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip(), ""
        except Exception as e:
            return "", f"Could not read PDF: {e}"

    if name.endswith(".docx") or name.endswith(".doc"):
        try:
            import docx
            doc = docx.Document(uploaded_file)
            text = "\n".join(p.text for p in doc.paragraphs)
            return text.strip(), ""
        except Exception as e:
            return "", f"Could not read the file: {e}"

    return "", f"Unsupported file type: {uploaded_file.name}"


def analyze_fit(cv_text: str, jd_text: str) -> dict:
    """
    Send CV and JD to Claude and return structured fit analysis.
    Returns a dict with: fit_score, strengths, gaps, quick_wins,
    recruiter_summary, full_response.
    Raises RuntimeError on API/key errors, ValueError on unparseable response.
    """

    client = _get_client()

    try:
        message = client.messages.create(
            # model="claude-sonnet-4-6",
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0.5,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"CV:\n{cv_text}",
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": f"JOB DESCRIPTION:\n{jd_text}",
                        },
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        clean = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(clean)

        # fit_score is derived, not opinion — compute it from the sub_scores
        # the model emitted so the rollup is always exact.
        s = result["sub_scores"]
        result["fit_score"] = round(
            0.35 * s["skills"]
            + 0.30 * s["experience"]
            + 0.25 * s["domain"]
            + 0.10 * s["education"]
        )

        result["full_response"] = raw
        return result

    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse Claude's response as JSON: {e}") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API error: {e}") from e


def tailor_cv(cv_text: str, jd_text: str) -> dict:
    """
    Send CV and JD to Claude and return a per-bullet tailoring diff.
    Returns a dict with: summary, tailored_bullets (list of
    {original, rewritten, reason}), full_response.
    Raises RuntimeError on API/key errors, ValueError on unparseable response.
    """

    client = _get_client()

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            temperature=0.5,
            system=[
                {
                    "type": "text",
                    "text": _TAILOR_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"CV:\n{cv_text}",
                            "cache_control": {"type": "ephemeral"},
                        },
                        {
                            "type": "text",
                            "text": f"JOB DESCRIPTION:\n{jd_text}",
                        },
                    ],
                }
            ],
        )

        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        clean = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(clean)

        result["full_response"] = raw
        return result

    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse Claude's response as JSON: {e}") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API error: {e}") from e

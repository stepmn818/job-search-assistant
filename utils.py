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
  "fit_score": <integer 0-100>,
  "sub_scores": {
    "skills": <integer 0-100>,
    "experience": <integer 0-100>,
    "domain": <integer 0-100>,
    "education": <integer 0-100>
  },
  "score_rationale": "<one sentence explaining why fit_score landed here, citing which sub-scores drove it>",
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

Final score rollup — fit_score MUST equal the weighted average of sub_scores, rounded to the nearest integer:
  fit_score = round(0.35*skills + 0.30*experience + 0.25*domain + 0.10*education)
Do not adjust fit_score outside this formula. If you feel the rollup is wrong, fix the sub_scores, not the total.

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


def _get_secret(key: str) -> str:
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


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

    api_key = os.environ.get("ANTHROPIC_API_KEY") or _get_secret("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not found. "
            "Add it to your .env file or Streamlit secrets."
        )

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
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
        result["full_response"] = raw
        return result

    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse Claude's response as JSON: {e}") from e
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API error: {e}") from e

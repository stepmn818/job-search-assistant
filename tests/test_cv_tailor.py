"""
Tests for pages/CV_Tailor.py — the CV tailoring diff page.

Run with:
    pytest tests/test_cv_tailor.py -v
"""
from streamlit.testing.v1 import AppTest

SAMPLE_TAILORING = {
    "summary": "Reworded one bullet to surface AWS, which the JD requires.",
    "tailored_bullets": [
        {
            "original": "Maintained backend services in Python.",
            "rewritten": "Maintained backend services in Python, deployed on AWS.",
            "reason": "Surfaces AWS, required by the JD.",
        },
    ],
    "full_response": "{}",
}


def _run(at):
    return at.run(timeout=20)


class TestEmptyState:
    def test_shows_info_when_no_tailoring_run_yet(self):
        at = AppTest.from_file("pages/CV_Tailor.py")
        _run(at)
        assert any("No tailoring has been run yet" in i.value for i in at.info)

    def test_no_summary_or_bullets_rendered_before_first_run(self):
        at = AppTest.from_file("pages/CV_Tailor.py")
        _run(at)
        assert at.markdown == []


class TestTailoringResult:
    def test_renders_summary_and_cv_name(self):
        at = AppTest.from_file("pages/CV_Tailor.py")
        at.session_state["tailor_result"] = dict(SAMPLE_TAILORING)
        at.session_state["tailor_cv_name"] = "Test CV"
        _run(at)

        assert any(SAMPLE_TAILORING["summary"] in i.value for i in at.info)
        assert any("Test CV" in c.value for c in at.caption)

    def test_renders_before_after_bullets(self):
        at = AppTest.from_file("pages/CV_Tailor.py")
        at.session_state["tailor_result"] = dict(SAMPLE_TAILORING)
        at.session_state["tailor_cv_name"] = "Test CV"
        _run(at)

        markdown_values = "\n".join(m.value for m in at.markdown)
        assert "Maintained backend services in Python." in markdown_values
        assert "Maintained backend services in Python, deployed on AWS." in markdown_values
        assert "Surfaces AWS, required by the JD." in markdown_values

    def test_empty_bullets_shows_success_message(self):
        at = AppTest.from_file("pages/CV_Tailor.py")
        at.session_state["tailor_result"] = {
            "summary": "No changes needed — the CV already matches the JD.",
            "tailored_bullets": [],
            "full_response": "{}",
        }
        _run(at)

        assert any("No bullets needed changes" in s.value for s in at.success)
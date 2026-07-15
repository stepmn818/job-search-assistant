"""
Tests for CV_Fit_Scorer.py — the Streamlit fit-scorer page.

Uses Streamlit's AppTest harness to drive the page without a browser.
`analyze_fit` is mocked so no real Claude API call is made.

Run with:
    pytest tests/test_cv_fit_scorer.py -v
"""
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import database

SAMPLE_ANALYSIS = {
    "sub_scores": {"skills": 80, "experience": 70, "domain": 60, "education": 50},
    "score_rationale": "Strong skills but weaker domain match.",
    "strengths": ["Python", "SQL"],
    "gaps": ["No cloud experience"],
    "quick_wins": ["Add an AWS certification"],
    "recruiter_summary": "Solid technical candidate, light on domain expertise.",
    "fit_score": 71,
    "full_response": "{}",
}


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Fresh, isolated SQLite file per test so runs don't touch the real db."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    return db_file


def _run(at):
    return at.run(timeout=20)


def _add_cv_via_paste(at, text="Experienced Python developer with 5 years of backend work.", name="Test CV"):
    at.sidebar.radio[0].set_value("Paste text")
    _run(at)
    at.sidebar.text_area(key="paste_input").set_value(text)
    _run(at)
    at.sidebar.text_input[0].set_value(name)
    _run(at)
    at.sidebar.button[0].click()
    _run(at)
    return at


def _add_jd(at, text="We need a backend engineer with 5 years of Python and AWS experience."):
    # The JD text area is the only text_area in the main body (the CV paste
    # box lives in the sidebar and is a separate query namespace).
    at.text_area[0].set_value(text)
    _run(at)
    return at


class TestInitialState:
    def test_warns_with_no_cv_and_no_jd(self, isolated_db):
        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        assert at.warning[0].value == "Add your CV in the sidebar to get started."

    def test_no_fit_analysis_section_before_first_run(self, isolated_db):
        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        headers = [s.value for s in at.subheader]
        assert "📊 Fit Analysis" not in headers


class TestCvLibrary:
    def test_paste_adds_cv_to_library_and_selects_it(self, isolated_db):
        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at)
        assert "Test CV" in at.session_state.cv_library
        assert at.session_state.active_cv_name == "Test CV"

    def test_paste_without_name_gets_auto_name(self, isolated_db):
        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at, name="")
        assert "Pasted CV 1" in at.session_state.cv_library

    def test_remove_from_library_clears_active_cv(self, isolated_db):
        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at)
        assert at.session_state.cv_library

        remove_btn = next(b for b in at.sidebar.button if "Remove" in b.label)
        remove_btn.click()
        _run(at)
        assert at.session_state.cv_library == {}
        assert at.session_state.active_cv_name is None

    def test_warning_disappears_once_cv_and_jd_present(self, isolated_db):
        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at)
        _add_jd(at)
        assert at.warning == []


class TestAnalyseFit:
    def test_error_when_analysing_without_cv(self, isolated_db):
        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_jd(at)
        analyse_btn = next(b for b in at.button if "Analyse" in b.label)
        analyse_btn.click()
        _run(at)
        assert any("provide your CV" in e.value for e in at.error)

    @patch("utils.analyze_fit")
    def test_successful_analysis_renders_scores(self, mock_analyze, isolated_db):
        mock_analyze.return_value = dict(SAMPLE_ANALYSIS)

        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at)
        _add_jd(at)

        analyse_btn = next(b for b in at.button if "Analyse" in b.label)
        analyse_btn.click()
        _run(at)

        mock_analyze.assert_called_once()
        assert at.session_state.analysis_result["fit_score"] == 71

        metrics = {m.label: m.value for m in at.metric}
        assert metrics["Fit Score"] == "71 / 100"
        assert metrics["Skills (35%)"] == "80 / 100"

        markdown_values = "\n".join(m.value for m in at.markdown)
        assert "Python" in markdown_values  # a strength
        assert "No cloud experience" in markdown_values  # a gap

    @patch("utils.analyze_fit")
    def test_api_error_is_shown_and_clears_result(self, mock_analyze, isolated_db):
        mock_analyze.side_effect = RuntimeError("Anthropic API error: boom")

        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at)
        _add_jd(at)

        analyse_btn = next(b for b in at.button if "Analyse" in b.label)
        analyse_btn.click()
        _run(at)

        assert any("boom" in e.value for e in at.error)
        assert at.session_state.analysis_result is None


class TestSaveToTracker:
    @patch("utils.analyze_fit")
    def test_save_persists_application_and_shows_confirmation(self, mock_analyze, isolated_db):
        mock_analyze.return_value = dict(SAMPLE_ANALYSIS)

        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at)
        _add_jd(at)
        next(b for b in at.button if "Analyse" in b.label).click()
        _run(at)

        at.text_input(key="save_company").set_value("Anthropic")
        _run(at)
        at.text_input(key="save_role").set_value("ML Engineer")
        _run(at)

        save_btn = next(b for b in at.button if "Save to tracker" in b.label)
        assert not save_btn.disabled
        save_btn.click()
        _run(at)

        app_id = at.session_state.saved_app_id
        assert app_id is not None

        saved = database.get_application(app_id)
        assert saved["company"] == "Anthropic"
        assert saved["role"] == "ML Engineer"
        assert saved["fit_score"] == 71
        assert saved["cv_name"] == "Test CV"

        assert any("Saved to tracker" in s.value for s in at.success)

    @patch("utils.analyze_fit")
    def test_save_button_disabled_until_company_and_role_filled(self, mock_analyze, isolated_db):
        mock_analyze.return_value = dict(SAMPLE_ANALYSIS)

        at = AppTest.from_file("CV_Fit_Scorer.py")
        _run(at)
        _add_cv_via_paste(at)
        _add_jd(at)
        next(b for b in at.button if "Analyse" in b.label).click()
        _run(at)

        save_btn = next(b for b in at.button if "Save to tracker" in b.label)
        assert save_btn.disabled

        at.text_input(key="save_company").set_value("Anthropic")
        _run(at)
        save_btn = next(b for b in at.button if "Save to tracker" in b.label)
        assert save_btn.disabled  # role still empty

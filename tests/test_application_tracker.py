"""
Tests for pages/Application_Tracker.py — the Streamlit application tracker page.

Uses Streamlit's AppTest harness to drive the page without a browser.

Run with:
    pytest tests/test_application_tracker.py -v
"""
import pytest
from streamlit.testing.v1 import AppTest

import database

PAGE = "pages/Application_Tracker.py"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Fresh, isolated SQLite file per test so runs don't touch the real db."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()
    return db_file


def _run(at):
    return at.run(timeout=20)


class TestEmptyState:
    def test_shows_info_when_no_applications_at_all(self, isolated_db):
        at = AppTest.from_file(PAGE)
        _run(at)
        at.radio[0].set_value("All")
        _run(at)
        assert any("No applications saved yet" in i.value for i in at.info)

    def test_shows_bucket_specific_message_when_filter_has_no_matches(self, isolated_db):
        # Default filter is "Active"; an Applied app is active, so switching
        # to "Archived" should hit the empty-bucket branch, not the no-apps one.
        app_id = database.insert_application(company="Acme", role="PM")
        database.update_application(app_id, status="Applied")

        at = AppTest.from_file(PAGE)
        _run(at)
        at.radio[0].set_value("Archived")
        _run(at)
        assert any("No applications in the" in i.value for i in at.info)


class TestTable:
    def test_lists_saved_applications(self, isolated_db):
        database.insert_application(
            company="Anthropic", role="ML Engineer", fit_score=85,
            sub_scores={"skills": 90, "experience": 80, "domain": 85, "education": 70},
        )
        database.insert_application(
            company="Acme", role="PM", fit_score=60,
        )

        at = AppTest.from_file(PAGE)
        _run(at)

        assert at.dataframe
        df = at.dataframe[0].value
        companies = set(df["Company"])
        assert companies == {"Anthropic", "Acme"}

    def test_sort_by_fit_score(self, isolated_db):
        database.insert_application(company="Low", role="r", fit_score=40)
        database.insert_application(company="High", role="r", fit_score=95)

        at = AppTest.from_file(PAGE)
        _run(at)
        sort_box = next(s for s in at.selectbox if s.label == "Sort by")
        sort_box.set_value("Fit score")
        _run(at)

        df = at.dataframe[0].value
        assert list(df["Company"]) == ["High", "Low"]


class TestEditForm:
    def test_selecting_an_application_shows_its_fields(self, isolated_db):
        database.insert_application(company="Anthropic", role="ML Engineer", fit_score=85)

        at = AppTest.from_file(PAGE)
        _run(at)

        company_input = next(
            ti for ti in at.text_input if ti.key and ti.key.startswith("edit_company_")
        )
        assert company_input.value == "Anthropic"

    def test_switching_status_to_interview_reveals_round_field(self, isolated_db):
        database.insert_application(company="Anthropic", role="ML Engineer", fit_score=85)

        at = AppTest.from_file(PAGE)
        _run(at)

        status_box = next(sb for sb in at.selectbox if sb.key and sb.key.startswith("edit_status_"))
        assert not any(ni.key and ni.key.startswith("edit_round_") for ni in at.number_input)

        status_box.set_value("Interview")
        _run(at)

        assert any(ni.key and ni.key.startswith("edit_round_") for ni in at.number_input)

    def test_switching_status_to_rejected_reveals_reason_field(self, isolated_db):
        database.insert_application(company="Anthropic", role="ML Engineer", fit_score=85)

        at = AppTest.from_file(PAGE)
        _run(at)

        status_box = next(sb for sb in at.selectbox if sb.key and sb.key.startswith("edit_status_"))
        status_box.set_value("Rejected")
        _run(at)

        assert any(ta.key and ta.key.startswith("edit_rejection_") for ta in at.text_area)

    def test_save_changes_persists_status_and_notes(self, isolated_db):
        app_id = database.insert_application(company="Anthropic", role="ML Engineer", fit_score=85)

        at = AppTest.from_file(PAGE)
        _run(at)

        status_box = next(sb for sb in at.selectbox if sb.key and sb.key.startswith("edit_status_"))
        status_box.set_value("Applied")
        _run(at)

        notes_area = next(ta for ta in at.text_area if ta.key and ta.key.startswith("edit_notes_"))
        notes_area.set_value("Referred by a friend")
        _run(at)

        save_btn = next(b for b in at.button if b.key and b.key.startswith("edit_save_"))
        save_btn.click()
        _run(at)

        row = database.get_application(app_id)
        assert row["status"] == "Applied"
        assert row["notes"] == "Referred by a friend"

    def test_save_rejects_empty_company(self, isolated_db):
        database.insert_application(company="Anthropic", role="ML Engineer", fit_score=85)

        at = AppTest.from_file(PAGE)
        _run(at)

        company_input = next(
            ti for ti in at.text_input if ti.key and ti.key.startswith("edit_company_")
        )
        company_input.set_value("   ")
        _run(at)

        save_btn = next(b for b in at.button if b.key and b.key.startswith("edit_save_"))
        save_btn.click()
        _run(at)

        assert any("cannot be empty" in e.value for e in at.error)

    def test_status_change_clears_stale_conditional_fields(self, isolated_db):
        app_id = database.insert_application(company="Anthropic", role="ML Engineer", fit_score=85)
        database.update_application(
            app_id, status="Rejected", rejection_reason="Not enough experience"
        )

        at = AppTest.from_file(PAGE)
        _run(at)
        # The saved app is "Rejected" (archived), invisible under the default
        # "Active" filter — switch to "All" so the edit form renders for it.
        at.radio[0].set_value("All")
        _run(at)

        status_box = next(sb for sb in at.selectbox if sb.key and sb.key.startswith("edit_status_"))
        status_box.set_value("Applied")
        _run(at)

        save_btn = next(b for b in at.button if b.key and b.key.startswith("edit_save_"))
        save_btn.click()
        _run(at)

        row = database.get_application(app_id)
        assert row["status"] == "Applied"
        assert row["rejection_reason"] is None

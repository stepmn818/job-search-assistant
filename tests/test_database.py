"""
Tests for database.py — SQLite persistence for saved applications.

Run with:
    pytest tests/test_database.py -v
"""
import sqlite3

import pytest

import database


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path, monkeypatch):
    """Fresh, isolated SQLite file per test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_file))
    database.init_db()
    return db_file


def _rewind_date_updated(app_id: int, when: str) -> None:
    """Force date_updated to a specific timestamp for deterministic ordering tests."""
    with sqlite3.connect(database.DB_PATH) as conn:
        conn.execute(
            "UPDATE applications SET date_updated = ? WHERE id = ?",
            (when, app_id),
        )


# ── init_db ───────────────────────────────────────────────────────────────────

class TestInitDb:

    def test_idempotent(self, db):
        # Already called once via the fixture; calling again must not error.
        database.init_db()
        database.init_db()

    def test_creates_table(self, db):
        with sqlite3.connect(database.DB_PATH) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='applications'"
            ).fetchone()
        assert row is not None


# ── insert + get roundtrip ────────────────────────────────────────────────────

class TestInsertAndGet:

    def test_roundtrip_with_sub_scores(self, db):
        sub_scores = {"skills": 75, "experience": 80, "domain": 65, "education": 60}
        app_id = database.insert_application(
            company="Anthropic",
            role="ML Engineer",
            cv_name="cv-main.pdf",
            jd_text="Looking for an ML engineer...",
            fit_score=72,
            sub_scores=sub_scores,
            jd_url="https://example.com/jobs/1",
            notes="Referred by Alex",
        )
        assert isinstance(app_id, int)

        row = database.get_application(app_id)
        assert row["company"] == "Anthropic"
        assert row["role"] == "ML Engineer"
        assert row["cv_name"] == "cv-main.pdf"
        assert row["jd_text"] == "Looking for an ML engineer..."
        assert row["fit_score"] == 72
        # JSON encoded on the way in, decoded on the way out — must survive intact.
        assert row["sub_scores"] == sub_scores
        assert row["jd_url"] == "https://example.com/jobs/1"
        assert row["notes"] == "Referred by Alex"
        # Defaults
        assert row["status"] == "Considering"
        assert row["interview_round"] is None
        assert row["rejection_reason"] is None
        assert row["not_applying_reason"] is None
        assert row["date_saved"] is not None
        assert row["date_updated"] is not None

    def test_get_missing_returns_none(self, db):
        assert database.get_application(9999) is None

    def test_insert_with_only_required_fields(self, db):
        app_id = database.insert_application(company="Acme", role="PM")
        row = database.get_application(app_id)
        assert row["company"] == "Acme"
        assert row["role"] == "PM"
        assert row["sub_scores"] is None
        assert row["fit_score"] is None


# ── update_application ────────────────────────────────────────────────────────

class TestUpdateApplication:

    def test_stamps_date_updated(self, db):
        app_id = database.insert_application(company="A", role="B")
        # Rewind to a known-old timestamp so the comparison is robust against
        # SQLite's 1-second CURRENT_TIMESTAMP granularity.
        _rewind_date_updated(app_id, "2020-01-01 00:00:00")

        database.update_application(app_id, status="Applied")

        row = database.get_application(app_id)
        assert row["status"] == "Applied"
        assert row["date_updated"] > "2020-01-01 00:00:00"

    def test_updates_multiple_fields(self, db):
        app_id = database.insert_application(company="A", role="B")
        database.update_application(
            app_id,
            status="Interview",
            interview_round=2,
            notes="phone screen done",
        )
        row = database.get_application(app_id)
        assert row["status"] == "Interview"
        assert row["interview_round"] == 2
        assert row["notes"] == "phone screen done"

    def test_rejects_unknown_field(self, db):
        app_id = database.insert_application(company="A", role="B")
        with pytest.raises(ValueError, match="unknown field"):
            database.update_application(app_id, fit_score=99)  # immutable post-save

    def test_rejects_invalid_status_via_check_constraint(self, db):
        app_id = database.insert_application(company="A", role="B")
        with pytest.raises(sqlite3.IntegrityError):
            database.update_application(app_id, status="Bogus")

    def test_no_fields_is_a_noop(self, db):
        app_id = database.insert_application(company="A", role="B")
        # Should not raise, should not change anything.
        database.update_application(app_id)
        row = database.get_application(app_id)
        assert row["status"] == "Considering"


# ── list_applications: filters ────────────────────────────────────────────────

class TestListFilter:

    def _insert_one_per_status(self):
        ids = {}
        for status in database.VALID_STATUSES:
            app_id = database.insert_application(company=status, role="role")
            if status != "Considering":  # 'Considering' is the default
                database.update_application(app_id, status=status)
            ids[status] = app_id
        return ids

    def test_all_returns_every_row(self, db):
        self._insert_one_per_status()
        rows = database.list_applications(status_filter="all")
        assert len(rows) == len(database.VALID_STATUSES)

    def test_active_filter(self, db):
        self._insert_one_per_status()
        rows = database.list_applications(status_filter="active")
        statuses = {r["status"] for r in rows}
        assert statuses == set(database.ACTIVE_STATUSES)

    def test_archived_filter(self, db):
        self._insert_one_per_status()
        rows = database.list_applications(status_filter="archived")
        statuses = {r["status"] for r in rows}
        assert statuses == set(database.ARCHIVED_STATUSES)

    def test_unknown_filter_raises(self, db):
        with pytest.raises(ValueError, match="status_filter"):
            database.list_applications(status_filter="weird")


# ── list_applications: sorting ────────────────────────────────────────────────

class TestListSort:

    def test_sort_by_fit_score_desc(self, db):
        low = database.insert_application(company="low", role="r", fit_score=40)
        high = database.insert_application(company="high", role="r", fit_score=90)
        mid = database.insert_application(company="mid", role="r", fit_score=65)

        rows = database.list_applications(sort_by="fit_score")
        assert [r["id"] for r in rows] == [high, mid, low]

    def test_sort_by_days_since_update_oldest_first(self, db):
        recent = database.insert_application(company="recent", role="r")
        oldest = database.insert_application(company="oldest", role="r")
        middle = database.insert_application(company="middle", role="r")

        _rewind_date_updated(oldest,  "2020-01-01 00:00:00")
        _rewind_date_updated(middle,  "2023-01-01 00:00:00")
        _rewind_date_updated(recent,  "2025-01-01 00:00:00")

        rows = database.list_applications(sort_by="days_since_update")
        assert [r["id"] for r in rows] == [oldest, middle, recent]

    def test_sort_by_date_saved_newest_first(self, db):
        # date_saved is auto-populated and immutable; rows inserted later
        # should appear first. But within the same second they tie — rewind
        # to make the order deterministic.
        first = database.insert_application(company="first", role="r")
        second = database.insert_application(company="second", role="r")
        third = database.insert_application(company="third", role="r")

        with sqlite3.connect(database.DB_PATH) as conn:
            conn.execute("UPDATE applications SET date_saved = ? WHERE id = ?",
                         ("2020-01-01 00:00:00", first))
            conn.execute("UPDATE applications SET date_saved = ? WHERE id = ?",
                         ("2023-01-01 00:00:00", second))
            conn.execute("UPDATE applications SET date_saved = ? WHERE id = ?",
                         ("2025-01-01 00:00:00", third))

        rows = database.list_applications(sort_by="date_saved")
        assert [r["id"] for r in rows] == [third, second, first]

    def test_unknown_sort_raises(self, db):
        with pytest.raises(ValueError, match="sort_by"):
            database.list_applications(sort_by="alphabetical")


# ── days_since_update derived field ───────────────────────────────────────────

class TestDaysSinceUpdate:

    def test_value_present_on_get(self, db):
        app_id = database.insert_application(company="A", role="B")
        row = database.get_application(app_id)
        assert "days_since_update" in row
        assert row["days_since_update"] is not None
        assert row["days_since_update"] >= 0

    def test_value_grows_with_age(self, db):
        app_id = database.insert_application(company="A", role="B")
        _rewind_date_updated(app_id, "2020-01-01 00:00:00")
        row = database.get_application(app_id)
        # Anything past Jan 2020 should be hundreds of days at minimum.
        assert row["days_since_update"] > 365

"""SQLite persistence for saved job applications."""
import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = "job_search.db"

VALID_STATUSES = (
    "Considering",
    "Applied",
    "Interview",
    "Offer",
    "Offer Accepted",
    "Rejected",
    "Not Applying",
)

ACTIVE_STATUSES = ("Considering", "Applied", "Interview", "Offer")
ARCHIVED_STATUSES = ("Offer Accepted", "Rejected", "Not Applying")

# Fields the tracker UI is allowed to mutate post-save.
# Excludes immutable snapshot fields (cv_name, jd_text, fit_score, sub_scores)
# and timestamps (handled internally).
_UPDATABLE_FIELDS = frozenset({
    "company",
    "role",
    "status",
    "interview_round",
    "notes",
    "rejection_reason",
    "not_applying_reason",
    "jd_url",
})

_SORT_SQL = {
    "date_saved": "date_saved DESC",
    "fit_score": "fit_score DESC",
    # Oldest-touched first = highest days-since-update first.
    "days_since_update": "date_updated ASC",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                company              TEXT NOT NULL,
                role                 TEXT NOT NULL,
                cv_name              TEXT,
                jd_text              TEXT,
                fit_score            INTEGER,
                sub_scores           TEXT,
                status               TEXT NOT NULL DEFAULT 'Considering'
                                     CHECK (status IN (
                                         'Considering','Applied','Interview',
                                         'Offer','Offer Accepted','Rejected','Not Applying'
                                     )),
                interview_round      INTEGER,
                notes                TEXT,
                rejection_reason     TEXT,
                not_applying_reason  TEXT,
                jd_url               TEXT,
                date_saved           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_updated         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def insert_application(
    company: str,
    role: str,
    cv_name: str | None = None,
    jd_text: str | None = None,
    fit_score: int | None = None,
    sub_scores: dict | None = None,
    jd_url: str | None = None,
    notes: str | None = None,
) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO applications
                (company, role, cv_name, jd_text, fit_score, sub_scores, jd_url, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company,
                role,
                cv_name,
                jd_text,
                fit_score,
                json.dumps(sub_scores) if sub_scores is not None else None,
                jd_url,
                notes,
            ),
        )
        return cursor.lastrowid


def update_application(app_id: int, **fields) -> None:
    if not fields:
        return
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Cannot update unknown field(s): {sorted(unknown)}")

    set_clauses = [f"{col} = ?" for col in fields]
    set_clauses.append("date_updated = CURRENT_TIMESTAMP")
    sql = f"UPDATE applications SET {', '.join(set_clauses)} WHERE id = ?"
    params = list(fields.values()) + [app_id]

    with _connect() as conn:
        conn.execute(sql, params)


def _row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    raw = data.get("sub_scores")
    data["sub_scores"] = json.loads(raw) if raw else None
    data["days_since_update"] = _days_since(data.get("date_updated"))
    return data


def _days_since(ts: str | None) -> int | None:
    if not ts:
        return None
    # SQLite CURRENT_TIMESTAMP is UTC in "YYYY-MM-DD HH:MM:SS" (naive).
    try:
        then = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).days


def get_application(app_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_applications(
    status_filter: str = "all",
    sort_by: str = "date_saved",
) -> list[dict]:
    status_filter = status_filter.lower()
    if status_filter == "active":
        placeholders = ",".join("?" * len(ACTIVE_STATUSES))
        where = f"WHERE status IN ({placeholders})"
        params: tuple = ACTIVE_STATUSES
    elif status_filter == "archived":
        placeholders = ",".join("?" * len(ARCHIVED_STATUSES))
        where = f"WHERE status IN ({placeholders})"
        params = ARCHIVED_STATUSES
    elif status_filter == "all":
        where = ""
        params = ()
    else:
        raise ValueError(f"Unknown status_filter: {status_filter!r}")

    if sort_by not in _SORT_SQL:
        raise ValueError(f"Unknown sort_by: {sort_by!r}")
    order = _SORT_SQL[sort_by]

    sql = f"SELECT * FROM applications {where} ORDER BY {order}"
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]
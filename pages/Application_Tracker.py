"""Application Tracker — Phase 2 page."""
import pandas as pd
import streamlit as st

import database

st.set_page_config(page_title="Application Tracker", page_icon="📋", layout="wide")
database.init_db()

st.title("📋 Application Tracker")
st.caption("Saved applications from your fit analyses. Edit status, notes, and outcomes as your search progresses.")


# ── controls ──────────────────────────────────────────────────────────────────

_SORT_LABEL_TO_KEY = {
    "Date saved": "date_saved",
    "Fit score": "fit_score",
    "Days since update": "days_since_update",
}

control_col1, control_col2 = st.columns([2, 1])
with control_col1:
    status_filter_label = st.radio(
        "Show",
        ["Active", "Archived", "All"],
        horizontal=True,
    )
with control_col2:
    sort_label = st.selectbox("Sort by", list(_SORT_LABEL_TO_KEY.keys()))

apps = database.list_applications(
    status_filter=status_filter_label.lower(),
    sort_by=_SORT_LABEL_TO_KEY[sort_label],
)


# ── empty state ───────────────────────────────────────────────────────────────

if not apps:
    if status_filter_label == "All":
        st.info("No applications saved yet. Run a fit analysis on the home page and click **Save to tracker**.")
    else:
        st.info(f"No applications in the **{status_filter_label}** bucket. Try switching filter.")
    st.stop()


# ── table ─────────────────────────────────────────────────────────────────────

def _truncate(text: str | None, limit: int = 60) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


display_rows = [
    {
        "ID": a["id"],
        "Company": a["company"],
        "Role": a["role"],
        "Fit Score": a["fit_score"],
        "Status": a["status"],
        "Round": a["interview_round"] if a["status"] == "Interview" else None,
        "Days since update": a["days_since_update"],
        "Notes": _truncate(a["notes"]),
    }
    for a in apps
]

st.dataframe(
    pd.DataFrame(display_rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "ID": st.column_config.NumberColumn(width="small"),
        "Fit Score": st.column_config.NumberColumn(format="%d"),
        "Round": st.column_config.NumberColumn(format="%d"),
        "Days since update": st.column_config.NumberColumn(format="%d days"),
    },
)


# ── edit form ─────────────────────────────────────────────────────────────────

st.divider()
st.subheader("✏️ Update Application Status")

labels = {a["id"]: f"#{a['id']} — {a['company']} / {a['role']}" for a in apps}
selected_id = st.selectbox(
    "Choose an application",
    options=list(labels.keys()),
    format_func=labels.get,
)
selected = next(a for a in apps if a["id"] == selected_id)


def _render_edit_form(app: dict) -> None:
    app_id = app["id"]

    # Always-visible identifying fields. Strip on read so an all-whitespace
    # entry counts as empty for the NOT NULL check below.
    new_company = st.text_input(
        "Company", value=app["company"], key=f"edit_company_{app_id}"
    ).strip()
    new_role = st.text_input(
        "Role", value=app["role"], key=f"edit_role_{app_id}"
    ).strip()

    new_status = st.selectbox(
        "Status",
        options=database.VALID_STATUSES,
        index=database.VALID_STATUSES.index(app["status"]),
        key=f"edit_status_{app_id}",
    )

    # Conditional fields — visibility is driven by the *current* selectbox
    # value, not the stored status, so toggling status reveals the right
    # field immediately without a save round-trip.
    new_round = None
    new_rejection = None
    new_not_applying = None

    if new_status == "Interview":
        new_round = st.number_input(
            "Interview round",
            min_value=1,
            step=1,
            value=app["interview_round"] or 1,
            key=f"edit_round_{app_id}",
        )

    if new_status == "Rejected":
        new_rejection = st.text_area(
            "Rejection reason (optional)",
            value=app["rejection_reason"] or "",
            key=f"edit_rejection_{app_id}",
            height=80,
        )

    if new_status == "Not Applying":
        new_not_applying = st.text_area(
            "Why not applying (optional)",
            value=app["not_applying_reason"] or "",
            key=f"edit_not_applying_{app_id}",
            height=80,
        )

    new_notes = st.text_area(
        "Notes", value=app["notes"] or "", key=f"edit_notes_{app_id}", height=100
    )
    new_jd_url = st.text_input(
        "JD URL", value=app["jd_url"] or "", key=f"edit_jd_url_{app_id}"
    )

    # Read-only context the user might want while editing.
    with st.expander("📎 Snapshot from analysis (read-only)"):
        st.write(f"**Fit score:** {app['fit_score']}")
        if app.get("sub_scores"):
            st.write("**Sub-scores:**", app["sub_scores"])
        st.write(f"**CV used:** {app['cv_name'] or '(none)'}")
        st.write(f"**Saved:** {app['date_saved']}")
        st.write(f"**Last updated:** {app['date_updated']}")

    if st.button("💾 Save changes", key=f"edit_save_{app_id}", type="primary"):
        if not new_company or not new_role:
            st.error("Company and Role cannot be empty.")
            return

        # Clear conditional fields that don't match the current status so the
        # row doesn't carry stale data (e.g. a rejection reason when status
        # is now 'Applied').
        fields = {
            "company": new_company,
            "role": new_role,
            "status": new_status,
            "interview_round": int(new_round) if new_status == "Interview" else None,
            "rejection_reason": (
                new_rejection.strip() or None if new_status == "Rejected" else None
            ),
            "not_applying_reason": (
                new_not_applying.strip() or None if new_status == "Not Applying" else None
            ),
            "notes": new_notes.strip() or None,
            "jd_url": new_jd_url.strip() or None,
        }
        database.update_application(app_id, **fields)
        st.toast("Changes saved ✅")
        st.rerun()


_render_edit_form(selected)

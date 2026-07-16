"""CV Tailor — Phase 3 page."""
import streamlit as st

st.set_page_config(page_title="CV Tailor", page_icon="✏️", layout="wide")

st.title("✏️ CV Tailor")
st.caption("Per-bullet rewrites suggested for your CV, tailored to the job description you analysed.")

result = st.session_state.get("tailor_result")

if not result:
    st.info(
        "No tailoring has been run yet. Go to the **🎯 CV Fit Scorer** page, "
        "run an analysis, then click **✏️ Tailor my CV**."
    )
    st.stop()

cv_name = st.session_state.get("tailor_cv_name")
if cv_name:
    st.caption(f"Based on CV: **{cv_name}**")

summary = result.get("summary", "")
if summary:
    st.info(summary)

bullets = result.get("tailored_bullets", [])

if not bullets:
    st.success("No bullets needed changes for this role — see the summary above.")
    st.stop()

st.divider()

for i, bullet in enumerate(bullets, start=1):
    st.markdown(f"**Bullet {i}** — _{bullet.get('reason', '')}_")
    col_before, col_after = st.columns(2)
    with col_before:
        st.markdown("**Original**")
        st.markdown(f"> {bullet.get('original', '')}")
    with col_after:
        st.markdown("**Rewritten**")
        st.markdown(f"> {bullet.get('rewritten', '')}")
    st.divider()
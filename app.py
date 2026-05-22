import streamlit as st
from utils import analyze_fit

st.set_page_config(
    page_title="AI Job Search Assistant",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 AI Job Search Assistant")
st.caption("Phase 1 — CV vs Job Description Fit Scorer")

# --- Sidebar: CV Upload or Paste ---
with st.sidebar:
    st.header("📄 Your CV")
    cv_input_method = st.radio("How do you want to provide your CV?", ["Paste text", "Upload your CV"])

    cv_text = ""
    if cv_input_method == "Paste text":
        cv_text = st.text_area("Paste your CV here", height=400, placeholder="Copy and paste the full text of your CV...")
    else:
        uploaded_file = st.file_uploader("Upload your CV", type=["txt", "pdf", "docx", "doc"])
        if uploaded_file:
            from utils import parse_uploaded_file
            cv_text, err = parse_uploaded_file(uploaded_file)
            if err:
                st.error(err)
            else:
                st.success("CV loaded ✅")

    if cv_text:
        st.info(f"CV loaded: {len(cv_text.split())} words")

# --- Main area: JD Input ---
st.subheader("📋 Job Description")
jd_text = st.text_area(
    "Paste the full job description here",
    height=300,
    placeholder="Paste the job description you want to analyse..."
)

col1, col2 = st.columns([1, 3])
with col1:
    analyse_btn = st.button("🔍 Analyse Fit", type="primary", use_container_width=True)
with col2:
    if not cv_text:
        st.warning("Add your CV in the sidebar to get started.")
    elif not jd_text:
        st.warning("Paste a job description above.")

# --- Analysis ---
if analyse_btn:
    if not cv_text:
        st.error("Please provide your CV in the sidebar first.")
    elif not jd_text:
        st.error("Please paste a job description.")
    else:
        try:
            with st.spinner("Analysing fit with Claude..."):
                result = analyze_fit(cv_text, jd_text)
        except Exception as e:
            st.error(str(e))
            result = {}

        if result:
            st.divider()
            st.subheader("📊 Fit Analysis")

            # Fit Score + sub-scores in one row
            score = result.get("fit_score", 0)
            sub_scores = result.get("sub_scores", {})

            fit_col, skills_col, exp_col, domain_col, edu_col = st.columns(5)
            with fit_col:
                st.markdown("##### Fit Score")
                st.metric(label="Fit Score", value=f"{score} / 100", label_visibility="collapsed")
                st.progress(score / 100)
            for col, label, key in [
                (skills_col, "Skills (35%)", "skills"),
                (exp_col, "Experience (30%)", "experience"),
                (domain_col, "Domain (25%)", "domain"),
                (edu_col, "Education (10%)", "education"),
            ]:
                with col:
                    value = sub_scores.get(key, 0)
                    st.markdown(f"##### {label}")
                    st.metric(label=label, value=f"{value} / 100", label_visibility="collapsed")
                    st.progress(value / 100)

            rationale = result.get("score_rationale", "")
            if rationale:
                st.caption(f"**Why this score:** {rationale}")

            st.divider()

            # Three columns for key results
            col_a, col_b, col_c = st.columns(3)

            with col_a:
                st.markdown("### ✅ Top Strengths")
                for s in result.get("strengths", []):
                    st.markdown(f"- {s}")

            with col_b:
                st.markdown("### ⚠️ Skill Gaps")
                for g in result.get("gaps", []):
                    st.markdown(f"- {g}")

            with col_c:
                st.markdown("### 💡 Quick Wins")
                for q in result.get("quick_wins", []):
                    st.markdown(f"- {q}")

            st.divider()

            # Recruiter summary
            st.markdown("### 🧑‍💼 One-Line Recruiter Summary")
            st.info(result.get("recruiter_summary", ""))

            # # Full reasoning
            # with st.expander("📝 Full reasoning from Claude"):
            #     st.write(result.get("full_response", ""))

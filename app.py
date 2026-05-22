import streamlit as st
from utils import analyze_fit, parse_uploaded_file

st.set_page_config(
    page_title="AI Job Search Assistant",
    page_icon="🎯",
    layout="wide"
)

st.title("🎯 AI Job Search Assistant")
st.caption("Phase 1 — CV vs Job Description Fit Scorer")

# Session-scoped CV library: {name: text}
if "cv_library" not in st.session_state:
    st.session_state.cv_library = {}
if "active_cv_name" not in st.session_state:
    st.session_state.active_cv_name = None

# --- Sidebar: CV library + add new ---
with st.sidebar:
    st.header("📄 Your CV")

    # Add a new CV
    st.markdown("**Add a new CV**")
    cv_input_method = st.radio(
        "Input method",
        ["Upload a file", "Paste text"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if cv_input_method == "Upload a file":
        uploaded_file = st.file_uploader("Upload your CV", type=["txt", "pdf", "docx", "doc"])
        if uploaded_file and uploaded_file.name not in st.session_state.cv_library:
            text, err = parse_uploaded_file(uploaded_file)
            if err:
                st.error(err)
            elif text:
                st.session_state.cv_library[uploaded_file.name] = text
                st.session_state.active_cv_name = uploaded_file.name
                st.success(f"Added '{uploaded_file.name}' ✅")
    else:
        pasted = st.text_area(
            "Paste your CV here",
            height=250,
            placeholder="Copy and paste the full text of your CV...",
            key="paste_input",
        )
        paste_name = st.text_input("Save as", placeholder="e.g. data-scientist-cv")
        if st.button("➕ Add to library", use_container_width=True, disabled=not pasted.strip()):
            final_name = paste_name.strip() or f"Pasted CV {len(st.session_state.cv_library) + 1}"
            st.session_state.cv_library[final_name] = pasted
            st.session_state.active_cv_name = final_name
            st.success(f"Added '{final_name}' ✅")

    # Library selector — drawn after inputs so newly-added CVs appear immediately
    if st.session_state.cv_library:
        st.divider()
        st.markdown("**📚 Your uploaded CVs**")
        names = list(st.session_state.cv_library.keys())
        if st.session_state.active_cv_name not in names:
            st.session_state.active_cv_name = names[0]
        selected = st.selectbox(
            "Active CV",
            options=names,
            index=names.index(st.session_state.active_cv_name),
        )
        st.session_state.active_cv_name = selected
        active_text = st.session_state.cv_library[selected]
        st.caption(f"{len(active_text.split())} words")
        if st.button("🗑️ Remove from library", use_container_width=True):
            del st.session_state.cv_library[selected]
            st.session_state.active_cv_name = next(iter(st.session_state.cv_library), None)
            st.rerun()

# Active CV text for analysis
cv_text = ""
if st.session_state.active_cv_name and st.session_state.active_cv_name in st.session_state.cv_library:
    cv_text = st.session_state.cv_library[st.session_state.active_cv_name]

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
            st.subheader(
                "📊 Fit Analysis",
                help=(
                    "**Scoring guide** (applies to Fit Score and each sub-score)\n\n"
                    "- **85–100** — Near-perfect match\n"
                    "- **70–84** — Strong match; gaps are minor\n"
                    "- **50–69** — Partial match with 1–2 significant gaps\n"
                    "- **30–49** — Weak match; missing key required items\n"
                    "- **0–29** — Poor match; core requirements unmet\n\n"
                    "**Fit Score** is a weighted rollup: "
                    "`0.35·skills + 0.30·experience + 0.25·domain + 0.10·education`"
                ),
            )

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

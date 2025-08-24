
import streamlit as st
import json
import pandas as pd
from pathlib import Path
from overview_full import render_overview
from single_solicitation_view import render_single_solicitation
from award_insights_view import render_award_insights


# ────────────────────────────────────────────────────────────────────────────
# CONFIG / DATA LOADING
# ────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "sam_results_pacific_cargo.json"

@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    df = pd.json_normalize(raw)

    if 'title' in df.columns:
        df['title'] = df['title'].apply(
            lambda x: x[0] if isinstance(x, (list, tuple)) else x
        )

    if 'status' in df.columns:
        df['status'] = df['status'].str.strip()

    return df

if not DATA_PATH.exists():
    st.error(f"⚠️ Data file not found at {DATA_PATH}. Place combined_results_test1.json next to dashboard.py or update DATA_PATH.")
    st.stop()

# ────────────────────────────────────────────────────────────────────────────
# CSS STYLING
# ────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.big-section-title {
    font-size: 1.4em;
    font-weight: 700;
    color: #2c3e50;
    margin-top: 1.2em;
    margin-bottom: 0.5em;
}
.section-divider {
    border-top: 2px solid #ddd;
    margin-top: 1em;
    margin-bottom: 1em;
}
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# SIDEBAR MODE SELECTION
# ────────────────────────────────────────────────────────────────────────────

mode = st.sidebar.radio(
    "Mode",
    ["Overview", "Single Solicitation", "Award Insights"]
,
    index=0
)

# ────────────────────────────────────────────────────────────────────────────
# VIEW ROUTING
# ────────────────────────────────────────────────────────────────────────────

if mode == "Overview":
    render_overview()

elif mode == "Single Solicitation":
    render_single_solicitation()

elif mode == "Award Insights":
    render_award_insights()

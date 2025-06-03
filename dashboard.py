import json
import pandas as pd
import streamlit as st
from pathlib import Path
from rapidfuzz import fuzz
from single_solicitation import process_single_url

# ────────────────────────────────────────────────────────────────────────────
# CONFIG / DATA LOADING
# ────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "combined_results_fixed1.json"

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
    st.error(f"⚠️ Data file not found at {DATA_PATH}. Place combined_results_fixed1.json next to dashboard.py or update DATA_PATH.")
    st.stop()

df = load_data(DATA_PATH)

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
    border-top: 1px solid #ddd;
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
    ["Overview", "Single Solicitation"],
    index=0
)

# ────────────────────────────────────────────────────────────────────────────
# OVERVIEW MODE
# ────────────────────────────────────────────────────────────────────────────

if mode == "Overview":
    st.title("Bid Ally – Opportunity Overview")

    st.sidebar.header("Filters")
    all_sources = sorted(df['source'].dropna().unique())
    selected_sources = st.sidebar.multiselect("Source", all_sources, default=all_sources)

    all_statuses = sorted(df['status'].dropna().unique())
    selected_statuses = st.sidebar.multiselect("Status", all_statuses, default=all_statuses)

    only_with_insights = st.sidebar.checkbox("Only show rows with insights")

    filtered = df[
        df['source'].isin(selected_sources) &
        df['status'].isin(selected_statuses)
    ]
    if only_with_insights:
        filtered = filtered[
            filtered['insights'].notna() &
            filtered['insights'].astype(str).str.strip().ne("")
        ]

    search_query = st.text_input(
        "🔍 Search",
        "",
        placeholder="e.g. Ukraine, drones, medical logistics, construction, demining etc."
    ).strip().lower()

    if search_query:
        def fuzzy_row_match(row, threshold=70):
            combined_text = ' '.join([
                str(row.get("title", "")),
                str(row.get("insights", "")),
                str(row.get("swot", "")),
                ' '.join(
                    [str(b) for art in row.get("news_impacts", []) for b in art.get("impact", [])]
                ) if row.get("news_impacts") else ""
            ]).lower()
            score = fuzz.partial_ratio(search_query, combined_text)
            return score >= threshold

        filtered = filtered[filtered.apply(lambda r: fuzzy_row_match(r), axis=1)]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Opportunities", int(filtered.shape[0]))

    open_mask = (
        filtered['status'].str.lower().str.contains("open") |
        filtered['status'].str.lower().str.contains("forthcoming") |
        filtered['status'].str.lower().str.contains("submission")
    )
    col2.metric("Open / Forthcoming", int(open_mask.sum()))

    with_insights_mask = (
        filtered['insights'].notna() & filtered['insights'].astype(str).str.len().gt(0)
    )
    col3.metric("With Insights", int(with_insights_mask.sum()))

    st.markdown("---")
    st.subheader(f"Results ({filtered.shape[0]})")

    if filtered.empty:
        st.info("No opportunities match the current filters.")
    else:
        for _, row in filtered.iterrows():
            header = (
                f"{row['title']}  :small_blue_diamond: **{row['status']}**  |  **{row['source']}**"
            )
            with st.expander(header, expanded=False):
                st.write(f"**Link:** [{row['link']}]({row['link']})")

                if row.get('naics'):
                    try:
                        st.write(f"**NAICS:** {row['naics'][0]}")
                    except Exception:
                        st.write(f"**NAICS:** {row['naics']}")

                if row.get('value'):
                    st.write(f"**Contract value:** {row['value']}")

                if row.get('insights'):
                    st.markdown('<div class="big-section-title">Insights</div>', unsafe_allow_html=True)
                    st.write(row['insights'])
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

                if row.get('swot'):
                    st.markdown('<div class="big-section-title">SWOT</div>', unsafe_allow_html=True)
                    st.write(row['swot'])
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

                if row.get('news_impacts'):
                    st.markdown('<div class="big-section-title">Related News</div>', unsafe_allow_html=True)
                    for art in row['news_impacts']:
                        art_title = art.get("article_title", art.get("title", "Untitled article"))
                        art_link = art.get("article_link", art.get("link", ""))
                        impact_text = art.get("impact", "")
                        if art_link:
                            st.markdown(f"- [{art_title}]({art_link})")
                        else:
                            st.markdown(f"- **{art_title}**")
                        st.markdown(f"    • {impact_text}")
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

                if not row.get('insights'):
                    st.markdown('<div class="big-section-title">Insights</div>', unsafe_allow_html=True)
                    st.markdown("**No Insights available**")
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

                if not row.get("news_impacts"):
                    st.markdown('<div class="big-section-title">Related News</div>', unsafe_allow_html=True)
                    st.markdown("**No Impact from Recent Events**")
                    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    st.markdown("""
        <style>
            .stExpander > div:first-child { font-weight: 600; }
        </style>
    """, unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# SINGLE SOLICITATION MODE
# ────────────────────────────────────────────────────────────────────────────

elif mode == "Single Solicitation":
    st.title("Bid Ally – Single Solicitation Insights")
    st.markdown("Paste a SAM.gov or EU Tenders link below, then click **Generate Insights**.")

    single_url = st.text_input("Solicitation URL", "")
    if st.button("Generate Insights") and single_url.strip():
        with st.spinner("Processing solicitation… this may take 30–60 seconds …"):
            try:
                row = process_single_url(single_url.strip())
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.stop()

        st.markdown("#### Basic Info")
        st.write(f"**Title:** {row.get('title','')}")
        st.write(f"**Status:** {row.get('status','')}")
        st.write(f"**Source:** {row.get('source','')}")

        if row.get("naics"):
            st.write(f"**NAICS:** {row['naics']}")

        if row.get("solicitation"):
            st.write(f"**Solicitation #:** {row['solicitation']}")

        st.write(f"**Link:** [{single_url.strip()}]({single_url.strip()})")

        if row.get("insights"):
            st.markdown('<div class="big-section-title">Insights</div>', unsafe_allow_html=True)
            st.write(row['insights'])
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

        if row.get("swot"):
            st.markdown('<div class="big-section-title">SWOT</div>', unsafe_allow_html=True)
            st.write(row['swot'])
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

        news_impacts = row.get("news_impacts", [])
        if isinstance(news_impacts, list) and news_impacts:
            st.markdown('<div class="big-section-title">Related News Impacts</div>', unsafe_allow_html=True)
            for art in news_impacts:
                art_title = art.get("article_title", "Untitled")
                art_link = art.get("article_link", "")
                impact_txt = art.get("impact", "")
                if art_link:
                    st.markdown(f"- [{art_title}]({art_link})")
                else:
                    st.markdown(f"- **{art_title}**")
                st.markdown(f"    • {impact_txt}")
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="big-section-title">Related News Impacts</div>', unsafe_allow_html=True)
            st.markdown("**No relevant news impacts found.**")
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

        st.markdown("---")
    else:
        st.info("Enter a valid SAM.gov or EU Tenders URL, then click **Generate Insights**.")

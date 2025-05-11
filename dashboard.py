


import json
import pandas as pd
import streamlit as st
from pathlib import Path
from rapidfuzz import fuzz


# ---------- CONFIG ----------
from pathlib import Path

# Resolves to the folder that contains dashboard.py
ROOT = Path(__file__).parent

DATA_PATH = ROOT / "combined_results_fixed1.json"   
# ---------- DATA ----------
@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    # ✅ NOTE the explicit encoding
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    df = pd.json_normalize(raw)

    # flatten lists that only hold one element
    if 'title' in df.columns:
        df['title'] = df['title'].apply(
            lambda x: x[0] if isinstance(x, (list, tuple)) else x
        )
    if 'status' in df.columns:
        df['status'] = df['status'].str.strip()

    return df



if not DATA_PATH.exists():
    st.error(f"⚠️ Data file not found at {DATA_PATH}. Place combined_results.json next to dashboard.py or update DATA_PATH.")
    st.stop()

df = load_data(DATA_PATH)

# ---------- SIDEBAR / FILTERS ----------
st.sidebar.header("Filters")

# Source filter
all_sources = sorted(df['source'].dropna().unique())
selected_sources = st.sidebar.multiselect("Source", all_sources, default=all_sources)

# Status filter
all_statuses = sorted(df['status'].dropna().unique())
selected_statuses = st.sidebar.multiselect("Status", all_statuses, default=all_statuses)

# Insights filter
only_with_insights = st.sidebar.checkbox("Only show rows with insights")

# Apply filters
filtered = df[df['source'].isin(selected_sources) & df['status'].isin(selected_statuses)]

if only_with_insights:
    filtered = filtered[filtered['insights'].notna() & filtered['insights'].astype(str).str.strip().ne("")]

# ---------- MAIN ----------
st.title("Bid Ally – Opportunity Overview")

# ---------- FUZZY SEARCH ----------
search_query = st.text_input("🔍 Search all fields", "").strip().lower()

if search_query:
    def fuzzy_row_match(row, threshold=70):
        # Combine relevant fields into a single text blob
        combined_text = ' '.join([
            str(row.get("title", "")),
            str(row.get("insights", "")),
            str(row.get("swot", "")),
            str(row.get("tags", "")),
            ' '.join(
                [str(b) for art in row.get("news_impacts", []) for b in art.get("impact_bullets", [])]
            ) if row.get("news_impacts") else ""
        ]).lower()

        # Calculate fuzzy match score
        score = fuzz.partial_ratio(search_query, combined_text)
        return score >= threshold

    filtered = filtered[filtered.apply(lambda row: fuzzy_row_match(row), axis=1)]


# KPI row
col1, col2, col3 = st.columns(3)
col1.metric("Total Opportunities", int(filtered.shape[0]))
open_mask = filtered['status'].str.lower().str.contains("open") | filtered['status'].str.lower().str.contains("forthcoming") | filtered['status'].str.lower().str.contains("submission")
col2.metric("Open / Forthcoming", int(open_mask.sum()))
with_insights = filtered['insights'].notna() & filtered['insights'].astype(str).str.len().gt(0)
col3.metric("With GPT Insights", int(with_insights.sum()))

st.markdown("---")

# ---------- CARD VIEW ----------
st.subheader(f"Results ({filtered.shape[0]})")

if filtered.empty:
    st.info("No opportunities match the current filters.")
else:
    for _, row in filtered.iterrows():
        header = f"{row['title']}  :small_blue_diamond: **{row['status']}**  |  **{row['source']}**"
        with st.expander(header, expanded=False):
            st.write(f"**Link:** [{row['link']}]({row['link']})")

            if row.get('naics'):
                st.write(f"**NAICS:** {row['naics'][0]}")

            if row.get('value'):
                st.write(f"**Contract value:** {row['value']}")

            # Tags
            if row.get('tags'):
                tags = ', '.join([t.strip() for t in row['tags'].split(';') if t.strip()])
                st.write(f"**Tags:** {tags}")

            # Insights
            if row.get('insights'):
                st.markdown("#### GPT Insights")
                st.write(row['insights'])

            # SWOT
            if row.get('swot'):
                st.markdown("#### SWOT")
                st.write(row['swot'])

            # Related news
            if row.get('news_impacts'):
                st.markdown("#### Related News")
                for art in row['news_impacts']:
                    bullets = art.get("impact_bullets") or art.get("impact")
                    title  = art.get("article_title") or art.get("title") or "Untitled article"
                    link   = art.get("link")         or art.get("url")

                    # parent line: clickable if link exists
                    if link:
                        st.markdown(f"- [{title}]({link})")
                    else:
                        st.markdown(f"- **{title}**")


                    if isinstance(bullets, list):
                        for b in bullets:
                            st.markdown(f"    • {b}")
                    else:
                        st.markdown(f"    • {bullets}")


            if not row.get('insights'):
                st.markdown("## Insights")
                st.markdown("**No Insights available**")

            if not row.get("news_impacts"):
                st.markdown("## Related News")
                st.markdown("**No Impact from Recent Events**")

# ---------- STYLE ----------
st.markdown("""
    <style>
        .stExpander > div:first-child {font-weight: 600;}
    </style>
""", unsafe_allow_html=True)

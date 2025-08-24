# overview_full.py
import json
import pandas as pd
import streamlit as st
from pathlib import Path
from rapidfuzz import fuzz
import re
from config import DATA_PATH


@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.json_normalize(raw)
    if 'title' in df.columns:
        df['title'] = df['title'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
    if 'status' in df.columns:
        df['status'] = df['status'].str.strip()
    return df

def render_overview():
    if not DATA_PATH.exists():
        st.error(f"⚠️ Data file not found at {DATA_PATH}.")
        return

    df = load_data(DATA_PATH)
    st.title("Bid Ally test – Opportunity Overview")

    st.sidebar.header("Filters")
    all_sources = sorted(df['source'].dropna().unique())
    selected_sources = st.sidebar.multiselect("Source", all_sources, default=all_sources)

    all_statuses = sorted(df['status'].dropna().unique())
    selected_statuses = st.sidebar.multiselect("Status", all_statuses, default=all_statuses)

    only_with_insights = st.sidebar.checkbox("Only show rows with insights")
    df["value_num"] = pd.to_numeric(df.get("value", None), errors="coerce")

    min_val, max_val = df["value_num"].min(), df["value_num"].max()
    if pd.notna(min_val) and pd.notna(max_val):
        st.sidebar.markdown("<div style='margin-top: 25px'></div>", unsafe_allow_html=True)
        valuation_range = st.sidebar.slider(
            "Filter by Estimated Contract Value",
            min_value=float(min_val),
            max_value=float(max_val),
            value=(float(min_val), float(max_val)),
            step=1000.0,
            format="%.0f"
        )
        st.sidebar.markdown(
            f"""<p style='font-weight: 500; margin-bottom: 0.5em;'>
            Selected Range: <span style='color:#2c3e50;'>${valuation_range[0]:,.0f}</span> – 
            <span style='color:#2c3e50;'>${valuation_range[1]:,.0f}</span>
            </p>""", 
            unsafe_allow_html=True
        )
        df = df[df["value_num"].between(valuation_range[0], valuation_range[1])]

    filtered = df[
        df['source'].isin(selected_sources) &
        df['status'].isin(selected_statuses)
    ]

    if only_with_insights:
        filtered = filtered[
            filtered['insights'].notna() & filtered['insights'].astype(str).str.strip().ne("")
        ]

    search_query = st.text_input("🔍 Search", "").strip().lower()
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
        return

    for _, row in filtered.iterrows():
        clean_title = row['title'].replace("$", "&#36;")
        header = f"{clean_title}  :small_blue_diamond: **{row['status']}**  |  **{row['source']}**"
        with st.expander(header, expanded=False):
            st.write(f"**Link:** [{row['link']}]({row['link']})")
            if row.get('naics'):
                st.write(f"**NAICS:** {row.get('naics')[0] if isinstance(row['naics'], list) else row['naics']}")
            if row.get('value'):
                try:
                    value_float = float(row['value'])
                    st.write(f"**Contract value:** ${value_float:,.0f}")
                except:
                    st.write(f"**Contract value:** {row['value']}")
                if row.get("value_confidence"):
                    color_map = {"high": "green", "medium": "orange", "low": "red"}
                    confidence = str(row["value_confidence"]).lower()
                    color = color_map.get(confidence, "gray")
                    st.markdown(
                        f"Contract value estimation confidence: <span style='color:{color}; font-weight:bold'>{row['value_confidence'].capitalize()}</span>",
                        unsafe_allow_html=True
                    )
            if row.get('insights'):
                st.markdown('<div class="big-section-title">Insights</div>', unsafe_allow_html=True)
                st.write(row['insights'])
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            if row.get("swot"):
                st.markdown('<div class="big-section-title">SWOT</div>', unsafe_allow_html=True)
                st.text(row['swot'])
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
            if row.get('news_impacts'):
                st.markdown('<div class="big-section-title">Related News</div>', unsafe_allow_html=True)
                for art in row['news_impacts']:
                    title = art.get("article_title", art.get("title", "Untitled article"))
                    link = art.get("article_link", art.get("link", ""))
                    text = art.get("impact", "")
                    st.markdown(f"- [{title}]({link})\n    • {text}")
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

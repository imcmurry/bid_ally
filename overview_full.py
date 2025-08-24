# overview_full.py
import json
import pandas as pd
import streamlit as st
from pathlib import Path
from rapidfuzz import fuzz
import re
from config import DATA_PATH


def escape_md_dollars(text: str) -> str:
    """
    Escape $ for Streamlit Markdown while preserving code blocks/spans.
    """
    if not isinstance(text, str) or not text:
        return text

    # Stash code blocks/spans so $ inside them isn't touched
    stash = []

    def _keep(m):
        stash.append(m.group(0))
        return f"__CODESLOT{len(stash)-1}__"

    tmp = re.sub(r"(```.*?```|`[^`]*`)", _keep, text, flags=re.S)
    tmp = tmp.replace("$", r"\$")
    for i, chunk in enumerate(stash):
        tmp = tmp.replace(f"__CODESLOT{i}__", chunk)
    return tmp


@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.json_normalize(raw)
    if "title" in df.columns:
        df["title"] = df["title"].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x)
    if "status" in df.columns:
        df["status"] = df["status"].str.strip()
    return df


def render_overview():
    if not DATA_PATH.exists():
        st.error(f"⚠️ Data file not found at {DATA_PATH}.")
        return

    df = load_data(DATA_PATH)
    st.title("Bid Ally test – Opportunity Overview")

    # Sidebar filters
    st.sidebar.header("Filters")
    all_sources = sorted(df["source"].dropna().unique())
    selected_sources = st.sidebar.multiselect("Source", all_sources, default=all_sources)

    all_statuses = sorted(df["status"].dropna().unique())
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
            format="%.0f",
        )
        # This is HTML (not markdown), so $ is fine here.
        st.sidebar.markdown(
            f"""<p style='font-weight: 500; margin-bottom: 0.5em;'>
            Selected Range: <span style='color:#2c3e50;'>${valuation_range[0]:,.0f}</span> – 
            <span style='color:#2c3e50;'>${valuation_range[1]:,.0f}</span>
            </p>""",
            unsafe_allow_html=True,
        )
        df = df[df["value_num"].between(valuation_range[0], valuation_range[1])]

    filtered = df[df["source"].isin(selected_sources) & df["status"].isin(selected_statuses)]

    if only_with_insights:
        filtered = filtered[
            filtered["insights"].notna() & filtered["insights"].astype(str).str.strip().ne("")
        ]

    # Search (fuzzy across title/insights/SWOT/news impacts)
    search_query = st.text_input("🔍 Search", "").strip().lower()
    if search_query:

        def fuzzy_row_match(row, threshold=70):
            combined_text = " ".join(
                [
                    str(row.get("title", "")),
                    str(row.get("insights", "")),
                    str(row.get("swot", "")),
                    " ".join(
                        [
                            # news impacts could be a string or list
                            (b if isinstance(b, str) else " ".join(map(str, b)))
                            for art in (row.get("news_impacts") or [])
                            for b in [art.get("impact", "")]
                        ]
                    ),
                ]
            ).lower()
            score = fuzz.partial_ratio(search_query, combined_text)
            return score >= threshold

        filtered = filtered[filtered.apply(lambda r: fuzzy_row_match(r), axis=1)]

    # KPIs
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Opportunities", int(filtered.shape[0]))

    open_mask = (
        filtered["status"].str.lower().str.contains("open")
        | filtered["status"].str.lower().str.contains("forthcoming")
        | filtered["status"].str.lower().str.contains("submission")
    )
    col2.metric("Open / Forthcoming", int(open_mask.sum()))

    with_insights_mask = filtered["insights"].notna() & filtered["insights"].astype(str).str.len().gt(0)
    col3.metric("With Insights", int(with_insights_mask.sum()))

    st.markdown("---")
    st.subheader(f"Results ({filtered.shape[0]})")

    if filtered.empty:
        st.info("No opportunities match the current filters.")
        return

    # Rows
    for _, row in filtered.iterrows():
        clean_title = escape_md_dollars(str(row.get("title", "")))
        clean_status = escape_md_dollars(str(row.get("status", "")))
        clean_source = escape_md_dollars(str(row.get("source", "")))

        header = f"{clean_title}  :small_blue_diamond: **{clean_status}**  |  **{clean_source}**"
        with st.expander(header, expanded=False):
            link = str(row.get("link", "")).strip()
            if link:
                st.write(f"**Link:** [{link}]({link})")

            if row.get("naics"):
                naics_val = row.get("naics")[0] if isinstance(row.get("naics"), list) else row.get("naics")
                st.write(f"**NAICS:** {naics_val}")

            if row.get("value") is not None:
                try:
                    value_float = float(row["value"])
                    # Escape the leading dollar (markdown)
                    st.write(f"**Contract value:** \\${value_float:,.0f}")
                except Exception:
                    st.write(f"**Contract value:** {escape_md_dollars(str(row['value']))}")

                if row.get("value_confidence"):
                    color_map = {"high": "green", "medium": "orange", "low": "red"}
                    confidence = str(row["value_confidence"]).lower()
                    color = color_map.get(confidence, "gray")
                    st.markdown(
                        f"Contract value estimation confidence: "
                        f"<span style='color:{color}; font-weight:bold'>{str(row['value_confidence']).capitalize()}</span>",
                        unsafe_allow_html=True,
                    )

            if row.get("insights"):
                st.markdown('<div class="big-section-title">Insights</div>', unsafe_allow_html=True)
                st.markdown(escape_md_dollars(str(row["insights"])))
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

            if row.get("swot"):
                st.markdown('<div class="big-section-title">SWOT</div>', unsafe_allow_html=True)
                st.markdown(escape_md_dollars(str(row["swot"])))
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

            if row.get("news_impacts"):
                st.markdown('<div class="big-section-title">Related News</div>', unsafe_allow_html=True)
                for art in row["news_impacts"]:
                    title = art.get("article_title", art.get("title", "Untitled article"))
                    link = art.get("article_link", art.get("link", ""))
                    impact = art.get("impact", "")
                    if isinstance(impact, list):
                        impact = " ".join(map(str, impact))
                    title_esc = escape_md_dollars(str(title))
                    impact_esc = escape_md_dollars(str(impact))
                    if link:
                        st.markdown(f"- [{title_esc}]({link})\n    • {impact_esc}")
                    else:
                        st.markdown(f"- {title_esc}\n    • {impact_esc}")
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

import json
import pandas as pd
import streamlit as st
from pathlib import Path
from rapidfuzz import fuzz
import re
from config import DATA_PATH

# ---------- Markdown/Input Normalizers ----------

_HEADING_BOLD = re.compile(r'^\s*\*\*(.+?)\*\*:?$', re.MULTILINE)

def normalize_markdown(md: str) -> str:
    """Make GPT-style text robust Markdown:
    - convert **Heading:** to '### Heading'
    - standardize bullets (•, –) to '-'
    - ensure blank lines before headings/lists
    - trim/pad sensible spacing
    """
    if not isinstance(md, str):
        return md
    s = md.strip()
    if not s:
        return s

    # Normalize line endings and stray non-breaking spaces
    s = s.replace('\r\n', '\n').replace('\r', '\n').replace('\xa0', ' ')

    # Remove common preambles
    s = re.sub(r'^\s*(Certainly|Here.*below)[^\n]*\n+', '', s, flags=re.IGNORECASE)

    # Convert bolded headings like **Strengths:** to real headings
    s = _HEADING_BOLD.sub(lambda m: f"### {m.group(1).strip()}", s)

    # Normalize bullets
    s = re.sub(r'^[ \t]*[•–]\s*', '- ', s, flags=re.MULTILINE)

    # Ensure blank lines before headings/lists
    s = re.sub(r'(?<!\n)\n(### )', r'\n\n\1', s)  # before headings
    s = re.sub(r'(?<!\n)\n(- )',    r'\n\n- ', s)  # before list items

    # Space around horizontal rules
    s = re.sub(r'\n?---\n?', '\n\n---\n\n', s)

    return s

def normalize_news_impacts(v):
    """Ensure news_impacts[].impact is always a list[str]."""
    if isinstance(v, list):
        for art in v:
            imp = art.get('impact')
            if isinstance(imp, str):
                art['impact'] = [imp.strip()] if imp.strip() else []
            elif not isinstance(imp, list):
                art['impact'] = []
    return v

# ---------- Data Loader ----------

@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    df = pd.json_normalize(raw)

    # Title: flatten lists and trim
    if 'title' in df.columns:
        df['title'] = df['title'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x).astype(str).str.strip()

    # Status: trim + Title Case for consistency (Open, Closed, etc.)
    if 'status' in df.columns:
        df['status'] = df['status'].astype(str).str.strip().str.title()

    # Clean Markdown fields so they render reliably
    for col in ('insights', 'swot'):
        if col in df.columns:
            df[col] = df[col].apply(normalize_markdown)

    # News impacts: schema consistency
    if 'news_impacts' in df.columns:
        df['news_impacts'] = df['news_impacts'].apply(normalize_news_impacts)

    return df

# ---------- UI ----------

def render_overview():
    if not DATA_PATH.exists():
        st.error(f"⚠️ Data file not found at {DATA_PATH}.")
        return

    df = load_data(DATA_PATH)
    st.title("Bid Ally test – Opportunity Overview")

    st.sidebar.header("Filters")
    all_sources = sorted(df['source'].dropna().unique()) if 'source' in df.columns else []
    selected_sources = st.sidebar.multiselect("Source", all_sources, default=all_sources)

    all_statuses = sorted(df['status'].dropna().unique()) if 'status' in df.columns else []
    selected_statuses = st.sidebar.multiselect("Status", all_statuses, default=all_statuses)

    only_with_insights = st.sidebar.checkbox("Only show rows with insights")

    # Numeric value handling for slider
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

    # Base filters
    filtered = df.copy()
    if selected_sources:
        filtered = filtered[filtered['source'].isin(selected_sources)]
    if selected_statuses:
        filtered = filtered[filtered['status'].isin(selected_statuses)]

    # Only rows with insights
    if only_with_insights and 'insights' in filtered.columns:
        filtered = filtered[
            filtered['insights'].notna() & filtered['insights'].astype(str).str.strip().ne("")
        ]

    # Search (fuzzy over multiple text fields)
    search_query = st.text_input("🔍 Search", "").strip().lower()
    if search_query:
        def fuzzy_row_match(row, threshold=70):
            combined_text = ' '.join([
                str(row.get("title", "")),
                str(row.get("insights", "")),
                str(row.get("swot", "")),
                ' '.join(
                    [str(b) for art in (row.get("news_impacts") or []) for b in (art.get("impact") or [])]
                )
            ]).lower()
            score = fuzz.partial_ratio(search_query, combined_text)
            return score >= threshold
        filtered = filtered[filtered.apply(lambda r: fuzzy_row_match(r), axis=1)]

    # KPI row
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Opportunities", int(filtered.shape[0]))

    if 'status' in filtered.columns:
        lower_status = filtered['status'].astype(str).str.lower()
        open_mask = (
            lower_status.str.contains("open") |
            lower_status.str.contains("forthcoming") |
            lower_status.str.contains("submission")
        )
        col2.metric("Open / Forthcoming", int(open_mask.sum()))
    else:
        col2.metric("Open / Forthcoming", 0)

    with_insights_mask = (
        filtered.get('insights', pd.Series(dtype=object)).notna() &
        filtered.get('insights', pd.Series(dtype=object)).astype(str).str.len().gt(0)
    )
    col3.metric("With Insights", int(with_insights_mask.sum()))

    st.markdown("---")
    st.subheader(f"Results ({filtered.shape[0]})")

    if filtered.empty:
        st.info("No opportunities match the current filters.")
        return

    for _, row in filtered.iterrows():
        title_raw = row.get('title', '')
        clean_title = str(title_raw).replace("$", "&#36;")  # avoid Markdown math trigger
        header = f"{clean_title}  :small_blue_diamond: **{row.get('status','')}**  |  **{row.get('source','')}**"
        with st.expander(header, expanded=False):
            link = row.get('link', '')
            if link:
                st.write(f"**Link:** [{link}]({link})")

            naics = row.get('naics')
            if naics:
                st.write(f"**NAICS:** {naics[0] if isinstance(naics, list) else naics}")

            if row.get('value') is not None:
                try:
                    value_float = float(row['value'])
                    st.write(f"**Contract value:** ${value_float:,.0f}")
                except Exception:
                    st.write(f"**Contract value:** {row['value']}")
                if row.get("value_confidence"):
                    color_map = {"high": "green", "medium": "orange", "low": "red"}
                    confidence = str(row["value_confidence"]).lower()
                    color = color_map.get(confidence, "gray")
                    st.markdown(
                        f"Contract value estimation confidence: "
                        f"<span style='color:{color}; font-weight:bold'>{str(row['value_confidence']).capitalize()}</span>",
                        unsafe_allow_html=True
                    )

            # Render cleaned Markdown
            insights = row.get('insights')
            if isinstance(insights, str) and insights.strip():
                st.markdown('<div class="big-section-title">Insights</div>', unsafe_allow_html=True)
                st.markdown(insights)
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

            swot = row.get('swot')
            if isinstance(swot, str) and swot.strip():
                st.markdown('<div class="big-section-title">SWOT</div>', unsafe_allow_html=True)
                st.markdown(swot)  # use markdown so headings/bullets show
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

            news = row.get('news_impacts') or []
            if isinstance(news, list) and news:
                st.markdown('<div class="big-section-title">Related News</div>', unsafe_allow_html=True)
                for art in news:
                    title = art.get("article_title", art.get("title", "Untitled article"))
                    link = art.get("article_link", art.get("link", ""))
                    impacts = art.get("impact") or []
                    impact_text = " ".join([str(x) for x in impacts]) if isinstance(impacts, list) else str(impacts)
                    st.markdown(f"- [{title}]({link})\n    • {impact_text}")
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

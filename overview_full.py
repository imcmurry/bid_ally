import json
import pandas as pd
import streamlit as st
from pathlib import Path
from rapidfuzz import fuzz
import re
from config import DATA_PATH

# ─────────────────────────────────────────────────────────────────────────────
# Markdown/Input Normalizers (match single-solicitation rendering fidelity)
# ─────────────────────────────────────────────────────────────────────────────

_HEADING_BOLD = re.compile(r'^\s*\*\*(.+?)\*\*:?$', re.MULTILINE)

def _normalize_tables(md: str) -> str:
    """
    Repair common GPT/pipe table issues so Streamlit Markdown renders them:
    - collapse '||' to '|'
    - ensure each table line starts/ends with a single '|'
    - insert a header-separator row if missing after the header
    - convert stray '--' to '---' (horizontal rule)
    """
    lines = md.split("\n")
    out = []
    i = 0

    def is_table_line(s: str) -> bool:
        return bool(re.match(r'^\s*\|', s)) or s.count("|") >= 2

    while i < len(lines):
        line = lines[i]

        # Fix stray '--' intended as horizontal rule
        if re.fullmatch(r'\s*--\s*', line):
            out.append('---')
            i += 1
            continue

        if is_table_line(line):
            # Collect contiguous table block (including blank lines inside)
            block = []
            while i < len(lines) and (is_table_line(lines[i]) or lines[i].strip() == ""):
                block.append(lines[i])
                i += 1

            # Keep only table lines (drop empty interior lines)
            tbl = [ln for ln in block if is_table_line(ln)]
            if tbl:
                # Clean pipes and spacing
                cleaned = []
                for ln in tbl:
                    ln = re.sub(r'\|\|+', '|', ln.strip())           # collapse multiple pipes
                    ln = re.sub(r'\s*\|\s*', '|', ln)                # trim around pipes
                    ln = f"|{ln.strip('|')}|"                        # ensure leading & trailing pipe
                    cleaned.append(ln)

                # Add header separator if missing
                if cleaned:
                    next_line = cleaned[1] if len(cleaned) > 1 else ""
                    has_sep = bool(re.fullmatch(r'\|(:?-{3,}:?\|)+', next_line.replace(' ', '')))
                    if not has_sep:
                        n_cols = max(1, cleaned[0].count('|') - 1)
                        sep = '|' + '|'.join([' --- ']*n_cols) + '|'
                        cleaned.insert(1, sep)

                # Ensure blank line before & after table
                if out and out[-1].strip():
                    out.append("")
                out.extend(cleaned)
                out.append("")
            else:
                out.extend(block)
        else:
            out.append(line)
            i += 1

    return "\n".join(out)

def normalize_markdown(md: str) -> str:
    """Make GPT-style prose robust Markdown across renderers."""
    if not isinstance(md, str):
        return md
    s = md.strip()
    if not s:
        return s

    s = s.replace('\r\n', '\n').replace('\r', '\n').replace('\xa0', ' ')

    # Remove chatty preambles
    s = re.sub(r'^\s*(Certainly|Here.*below)[^\n]*\n+', '', s, flags=re.IGNORECASE)

    # Convert **Heading:** → ### Heading
    s = _HEADING_BOLD.sub(lambda m: f"### {m.group(1).strip()}", s)

    # Normalize bullets (•, –) → '-'
    s = re.sub(r'^[ \t]*[•–]\s*', '- ', s, flags=re.MULTILINE)

    # Ensure blank lines before headings/lists
    s = re.sub(r'(?<!\n)\n(### )', r'\n\n\1', s)   # before headings
    s = re.sub(r'(?<!\n)\n(- )',    r'\n\n- ', s)  # before list items

    # Normalize horizontal rules
    s = re.sub(r'\n?---\n?', '\n\n---\n\n', s)

    # Fix tables last
    s = _normalize_tables(s)

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

# ─────────────────────────────────────────────────────────────────────────────
# Data Loader
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    df = pd.json_normalize(raw)

    # Title: flatten lists and trim
    if 'title' in df.columns:
        df['title'] = df['title'].apply(lambda x: x[0] if isinstance(x, (list, tuple)) else x).astype(str).str.strip()

    # Status: normalize for filtering counters
    if 'status' in df.columns:
        df['status'] = df['status'].astype(str).str.strip().str.title()

    # Clean Markdown fields so they render like single view
    for col in ('insights', 'swot'):
        if col in df.columns:
            df[col] = df[col].apply(normalize_markdown)

    # News impacts schema consistency
    if 'news_impacts' in df.columns:
        df['news_impacts'] = df['news_impacts'].apply(normalize_news_impacts)

    return df

# ─────────────────────────────────────────────────────────────────────────────
# Overview UI (styled like single_solicitation_view, but per-row in an expander)
# ─────────────────────────────────────────────────────────────────────────────

def render_overview():
    if not DATA_PATH.exists():
        st.error(f"⚠️ Data file not found at {DATA_PATH}.")
        return

    df = load_data(DATA_PATH)
    st.title("Bid Ally – Opportunity Overview")

    st.sidebar.header("Filters")
    all_sources = sorted(df['source'].dropna().unique()) if 'source' in df.columns else []
    selected_sources = st.sidebar.multiselect("Source", all_sources, default=all_sources)

    all_statuses = sorted(df['status'].dropna().unique()) if 'status' in df.columns else []
    selected_statuses = st.sidebar.multiselect("Status", all_statuses, default=all_statuses)

    only_with_insights = st.sidebar.checkbox("Only show rows with insights")

    # Value slider
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

    # Apply filters
    filtered = df.copy()
    if selected_sources:
        filtered = filtered[filtered['source'].isin(selected_sources)]
    if selected_statuses:
        filtered = filtered[filtered['status'].isin(selected_statuses)]
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
                ' '.join([str(b) for art in (row.get("news_impacts") or [])
                          for b in (art.get("impact") or [])])
            ]).lower()
            score = fuzz.partial_ratio(search_query, combined_text)
            return score >= threshold
        filtered = filtered[filtered.apply(lambda r: fuzzy_row_match(r), axis=1)]

    # KPI row
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Opportunities", int(filtered.shape[0]))
    if 'status' in filtered.columns:
        s_lower = filtered['status'].astype(str).str.lower()
        open_mask = (
            s_lower.str.contains("open") |
            s_lower.str.contains("forthcoming") |
            s_lower.str.contains("submission")
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

    # Render each opportunity using the single-solicitation section order
    for _, row in filtered.iterrows():
        title_raw = row.get('title', '')
        clean_title = str(title_raw).replace("$", "&#36;")  # avoid math mode trigger in md

        header = f"{clean_title}  :small_blue_diamond: **{row.get('status','')}**  |  **{row.get('source','')}**"
        with st.expander(header, expanded=False):
            st.markdown("#### Basic Info")
            if row.get('link'):
                st.write(f"**Link:** [{row['link']}]({row['link']})")
            if row.get("naics"):
                naics = row["naics"][0] if isinstance(row["naics"], list) else row["naics"]
                st.write(f"**NAICS:** {naics}")
            if row.get("solicitation"):
                st.write(f"**Solicitation #:** {row['solicitation']}")
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

            insights = row.get('insights')
            if isinstance(insights, str) and insights.strip():
                st.markdown('<div class="big-section-title">Insights</div>', unsafe_allow_html=True)
                st.markdown(insights)   # cleaned markdown (lists + tables)
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

            swot = row.get('swot')
            if isinstance(swot, str) and swot.strip():
                st.markdown('<div class="big-section-title">SWOT</div>', unsafe_allow_html=True)
                st.markdown(swot)       # cleaned markdown (lists + tables)
                st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

            news = row.get('news_impacts') or []
            st.markdown('<div class="big-section-title">Related News</div>', unsafe_allow_html=True)
            if isinstance(news, list) and news:
                for art in news:
                    title = art.get("article_title", art.get("title", "Untitled article"))
                    link = art.get("article_link", art.get("link", ""))
                    impacts = art.get("impact") or []
                    impact_text = " ".join([str(x) for x in impacts]) if isinstance(impacts, list) else str(impacts)
                    if link:
                        st.markdown(f"- [{title}]({link})\n    • {impact_text}")
                    else:
                        st.markdown(f"- **{title}**\n    • {impact_text}")
            else:
                st.markdown("**No relevant news impacts found.**")
            st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

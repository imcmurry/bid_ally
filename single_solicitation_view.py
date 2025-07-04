
import streamlit as st
from single_solicitation import process_single_url

def render_single_solicitation():
    st.title("Bid Ally – Single Solicitation Insights")
    st.markdown("Paste a SAM.gov or EU Tenders link below, then click **Generate Insights**.")

    single_url = st.text_input("Solicitation URL", "")
    if st.button("Generate Insights") and single_url.strip():
        with st.spinner("Processing solicitation… this may take 30–60 seconds …"):
            try:
                row = process_single_url(single_url.strip())
            except Exception as e:
                st.error(f"❌ Error: {e}")
                return

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

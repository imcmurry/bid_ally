import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
from config import DB_PATH, company_info, PERPLEXITY_KEY
from usaspending import get_all_usaspending_insights, push_insights_to_db
from gpt_analysis import generate_chart_insight, generate_competitor_positioning_insight, generate_trend_insight_by_year

@st.cache_data(show_spinner=False)
def load_sql_table(table_name: str) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

def render_award_insights():
    st.title("USAspending Award Insights")

    # ────────────── INPUT ──────────────
    naics_code = st.text_input("Enter a NAICS code:", value="621999")



    if naics_code:
        with sqlite3.connect(DB_PATH) as conn:
            runs_df = pd.read_sql_query(
                "SELECT * FROM usaspending_runs WHERE naics_code = ? ORDER BY timestamp DESC LIMIT 1",
                conn,
                params=(naics_code,)
            )

        force_rerun = False

        if not runs_df.empty:
            run_id = runs_df["run_id"].iloc[0]
            top_df = load_sql_table("usaspending_top_recipients")
            top_df = top_df[top_df["run_id"] == run_id]

            if top_df.empty:
                st.info("🔁 Existing data was empty — refreshing from source...")
                force_rerun = True
            else:
                st.success(f"✅ Results for: {naics_code}")
                yearly_df = load_sql_table("usaspending_yearly_totals")
                yearly_df = yearly_df[yearly_df["run_id"] == run_id]

                state_df = load_sql_table("usaspending_awards_by_state")
                state_df = state_df[state_df["run_id"] == run_id]

                state_yearly_df = load_sql_table("usaspending_state_yearly_trends")
                state_yearly_df = state_yearly_df[state_yearly_df["run_id"] == run_id]

        if runs_df.empty or force_rerun:
            st.warning(f"⚡ Collecting data for NAICS {naics_code}... Please wait up to 30 seconds.")
            insights = get_all_usaspending_insights(naics_code)

            if any(not df.empty for df in insights.values()):
                push_insights_to_db(insights, naics_code)
                st.success(f"✅ Data for NAICS {naics_code} collected and saved.")

                top_df = insights["top_recipients"].copy()
                yearly_df = insights["yearly_totals"].copy()
                state_df = insights["awards_by_state"].copy()
                state_yearly_df = insights["state_yearly_trends"].copy()
            else:
                st.warning(f"⚠️ No contract award data found for NAICS {naics_code}. Nothing was saved.")
                top_df = yearly_df = state_df = state_yearly_df = pd.DataFrame()

        # ────────────── CHART 1 ──────────────
        st.subheader("Top Recipients by Total Award Value")
        top_df = top_df.sort_values("total_awarded", ascending=False).head(10)
        fig_top = px.bar(
            top_df,
            x="total_awarded",
            y="recipient_name",
            orientation="h",
            labels={"recipient_name": "Recipient", "total_awarded": "Total Awarded ($)"},
            title="Top 10 Recipients by Federal Award Value"
        )
        fig_top.update_layout(
            yaxis={'categoryorder': 'total ascending'},
            xaxis_tickformat=",",
            height=500,
            xaxis=dict(showgrid=True, gridcolor="lightgray", gridwidth=1.2)
        )
        st.plotly_chart(fig_top, use_container_width=True)
        with st.spinner("Analyzing competitors with Perplexity..."):
            insight_1 = generate_competitor_positioning_insight(top_df, company_info, perplexity_key=PERPLEXITY_KEY)
        st.markdown(f"**Competitive Insight:** {insight_1}")


        # ────────────── CHART 2 ──────────────
        st.subheader("Total Award Value By Year")
        yearly_df["year"] = yearly_df["year"].astype(int)
        yearly_df = yearly_df[yearly_df["year"] >= 2010].sort_values("year")
        yearly_df["smoothed"] = yearly_df["total_awarded"].rolling(window=3, min_periods=1).mean()
        fig_year = px.bar(
            yearly_df,
            x="year",
            y="total_awarded",
            labels={"year": "Year", "total_awarded": "Total Award Value ($)"},
            title="Total Award Value By Year",
            color_discrete_sequence=["#1f77b4"]
        )
        fig_year.add_scatter(
            x=yearly_df["year"],
            y=yearly_df["smoothed"],
            mode="lines",
            name="3-Year Rolling Avg",
            line=dict(color="red", width=2),
        )
        fig_year.update_layout(
            xaxis=dict(tickmode="linear"),
            yaxis_tickformat=",",
            height=500,
            xaxis_title="Year",
            yaxis_title="Total Award Value ($)",
            xaxis_tickangle=45,
            showlegend=False
        )
        st.plotly_chart(fig_year, use_container_width=True)
        with st.spinner("Analyzing strategic insight..."):
            insight_2 = generate_trend_insight_by_year(
                yearly_df,
                "Total Award Value By Year",
                company_info,
                naics_code=naics_code,
                perplexity_key=PERPLEXITY_KEY
            )

        st.markdown(f"**Insight:** {insight_2}")

        # ────────────── CHART 3 ──────────────
        st.subheader("Award Value by State (Interactive Map)")
        fig_map = px.choropleth(
            state_df,
            locations="state",
            locationmode="USA-states",
            color="total_awarded",
            color_continuous_scale="Blues",
            scope="usa",
            labels={"total_awarded": "Total Awarded ($)"},
            title="Total Federal Award Amount by State"
        )
        st.plotly_chart(fig_map, use_container_width=True)
        with st.spinner("Analyzing strategic insight..."):
            insight_3 = generate_chart_insight(state_df, "Total Award Value by State", company_info)
        st.markdown(f"**Insight:** {insight_3}")

        # ────────────── CHART 4 ──────────────
        st.subheader("Average Year-over-Year Growth by State")
        state_yearly_df = state_yearly_df.sort_values(["state", "year"])
        state_yearly_df["year"] = state_yearly_df["year"].astype(int)
        state_yearly_df["pct_change"] = state_yearly_df.groupby("state")["total_awarded"].pct_change()
        growth_summary = (
            state_yearly_df.groupby("state")["pct_change"]
            .mean()
            .reset_index()
            .rename(columns={"pct_change": "avg_growth_rate"})
        )
        growth_summary["avg_growth_rate_percent"] = growth_summary["avg_growth_rate"] * 100
        fig_growth = px.choropleth(
            growth_summary,
            locations="state",
            locationmode="USA-states",
            color="avg_growth_rate_percent",
            color_continuous_scale=px.colors.diverging.RdYlGn,
            range_color=(-50, 100),
            scope="usa",
            labels={"avg_growth_rate_percent": "Avg YoY Growth (%)"},
            title="Average YoY Federal Contract Growth by State"
        )
        st.plotly_chart(fig_growth, use_container_width=True)
        with st.spinner("Analyzing strategic insight..."):
            insight_4 = generate_chart_insight(growth_summary, "YoY Growth by State", company_info)
        st.markdown(f"**Insight:** {insight_4}")


import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import matplotlib.pyplot as plt
import seaborn as sns
from config import DB_PATH

@st.cache_data(show_spinner=False)
def load_sql_table(table_name: str) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

def render_award_insights():
    st.title("USAspending Award Insights")

    # ────────────────
    # Top Recipients – Horizontal Bar Chart
    # ────────────────
    top_df = load_sql_table("usaspending_top_recipients")
    top_df = top_df.sort_values("total_awarded", ascending=False).head(10)

    st.subheader("Top Recipients by Total Award Value")

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
        xaxis=dict(
            showgrid=True,
            gridcolor="lightgray",     # Subtle grid color
            gridwidth=1.2              # Slightly bolder than default (default is ~1.0)
        )
    )
    st.plotly_chart(fig_top, use_container_width=True)

    # ───────────────────────────────
    # Yearly Totals (Bar + Smoothing)
    # ───────────────────────────────

    yearly_df = load_sql_table("usaspending_yearly_totals")
    st.subheader("Total Award Value By Year")

    # Clean and filter
    yearly_df["year"] = yearly_df["year"].astype(int)
    yearly_df = yearly_df[yearly_df["year"] >= 2010]
    yearly_df = yearly_df.sort_values("year")
    yearly_df["smoothed"] = yearly_df["total_awarded"].rolling(window=3, min_periods=1).mean()

    # Create Plotly bar + line chart
    fig_year = px.bar(
        yearly_df,
        x="year",
        y="total_awarded",
        labels={"year": "Year", "total_awarded": "Total Award Value ($)"},
        title="Total Award Value By Year",
        color_discrete_sequence=["#1f77b4"],  # Matching blue
    )

    # Add smoothed line
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


    # ────────────────────────
    # Awards by State (Map)
    # ────────────────────────
    state_df = load_sql_table("usaspending_awards_by_state")
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

    # ───────────────────────────────
    # State Trends (Year-over-Year)
    # ───────────────────────────────
    state_yearly_df = load_sql_table("usaspending_state_yearly_trends")
    st.subheader("Year-over-Year Trends by State")
    selected_state = st.selectbox("Select a state", sorted(state_yearly_df['state'].dropna().unique()))
    filtered = state_yearly_df[state_yearly_df['state'] == selected_state]
    st.line_chart(filtered.set_index("year")["total_awarded"])



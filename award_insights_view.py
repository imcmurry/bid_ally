
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

    # Top Recipients
    top_df = load_sql_table("usaspending_top_recipients")
    st.subheader("Top Recipients by Total Award Value")
    st.bar_chart(top_df.set_index("recipient_name")[:10])

    # Yearly Totals (Bar chart with smoothed line)
    yearly_df = load_sql_table("usaspending_yearly_totals")
    st.subheader("Total Contract Awards by Year")

    fig, ax = plt.subplots()

    # Clean and filter
    yearly_df["year"] = pd.to_numeric(yearly_df["year"], errors="coerce").astype("Int64")
    yearly_df = yearly_df.dropna(subset=["year"])
    yearly_df = yearly_df.sort_values("year")
    yearly_df["year_int"] = yearly_df["year"]
    yearly_df = yearly_df[yearly_df["year_int"] >= 2010]

    # Convert to millions
    yearly_df["award_millions"] = yearly_df["total_awarded"] / 1e6
    yearly_df["smoothed"] = yearly_df["award_millions"].rolling(window=3, min_periods=1).mean()

    # Plot
    sns.barplot(x="year", y="award_millions", data=yearly_df, color="skyblue", ax=ax)
    ax.plot(yearly_df["year"], yearly_df["smoothed"], color="red", linewidth=2)

    # Fix labels and format
    ax.set_xlabel("Year")
    ax.set_ylabel("Total Award Value ($ Millions)")
    ax.set_xticklabels(yearly_df["year"], rotation=45)
    ax.ticklabel_format(style='plain', axis='y')

    st.pyplot(fig)




    # Awards by State – Interactive U.S. map
    state_df = load_sql_table("usaspending_awards_by_state")
    st.subheader("Award Value by State (Interactive Map)")
    fig_map = px.choropleth(
        state_df,
        locations="state",
        locationmode="USA-states",
        color="total_awarded",
        color_continuous_scale="Blues",
        scope="usa",
        labels={'total_awarded': 'Total Awarded ($)'},
        title="Total Federal Award Amount by State"
    )
    st.plotly_chart(fig_map, use_container_width=True)

    # State Trends
    state_yearly_df = load_sql_table("usaspending_state_yearly_totals")
    st.subheader("Year-over-Year Trends by State")
    selected_state = st.selectbox("Select a state", sorted(state_yearly_df['state'].dropna().unique()))
    filtered = state_yearly_df[state_yearly_df['state'] == selected_state]
    st.line_chart(filtered.set_index("year")["total_awarded"])

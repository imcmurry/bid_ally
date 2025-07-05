
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
    top_df = top_df.sort_values(by="total_awarded", ascending=False).head(10)
    st.subheader("Top Recipients by Total Award Value")

    # Yearly Totals (Bar chart with smoothed line)
    yearly_df = load_sql_table("usaspending_yearly_totals")
    st.subheader("Total Contract Awards by Year")

    fig, ax = plt.subplots()

    # Ensure year is treated as a categorical string
    yearly_df["year"] = yearly_df["year"].astype(int)
    yearly_df = yearly_df[yearly_df["year"] >= 2010]
    yearly_df["year"] = yearly_df["year"].astype(int).astype(str)
    yearly_df = yearly_df.sort_values("year")
    

    # Bar plot using categorical years
    sns.barplot(x="year", y="total_awarded", data=yearly_df, color="skyblue", ax=ax)

    # Add smoothed moving average line (numeric x-values for the line)
    yearly_df["year_int"] = yearly_df["year"].astype(int)
    yearly_df["smoothed"] = yearly_df["total_awarded"].rolling(window=3, min_periods=1).mean()
    ax.plot(yearly_df["year"], yearly_df["smoothed"], color="red", linewidth=2)

    # Fix labels
    ax.set_xlabel("Year")
    ax.set_ylabel("Total Award Value (Million $)")
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

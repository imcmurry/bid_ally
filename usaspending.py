# usaspending.py
import requests
import pandas as pd
import time
import sqlite3
import uuid
from datetime import datetime

def fetch_all_awards(naics_code, lower_bound=1_000_000, upper_bound=25_000_000, page_size=100):
    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    headers = {"Content-Type": "application/json"}
    all_results = []
    page = 1

    while True:
        payload = {
            "filters": {
                "time_period": [{"start_date": "2007-10-01", "end_date": "2025-09-30"}],
                "award_type_codes": ["A", "B", "C", "D"],
                "award_amounts": [{"lower_bound": lower_bound, "upper_bound": upper_bound}],
                "naics_codes": [naics_code]
            },
            "fields": [
                "Award ID", "Recipient Name", "Award Amount", "Total Outlays", "Description",
                "Contract Award Type", "Recipient UEI", "Recipient Location",
                "Primary Place of Performance", "def_codes", "COVID-19 Obligations", "COVID-19 Outlays",
                "Infrastructure Obligations", "Infrastructure Outlays",
                "Awarding Agency", "Awarding Sub Agency",
                "Start Date", "End Date", "NAICS", "PSC",
                "recipient_id", "prime_award_recipient_id"
            ],
            "page": page,
            "limit": page_size,
            "sort": "Award Amount",
            "order": "desc",
            "subawards": False
        }

        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            print(f"❌ API error: {response.status_code}")
            print(response.text)
            break

        results = response.json().get("results", [])
        if not results:
            break

        all_results.extend(results)
        print(f"📄 Page {page} pulled ({len(results)} records)")
        page += 1
        time.sleep(0.4)  # Be respectful to API

    df = pd.json_normalize(all_results)
    return df


# ───────────────────────────────────────────────────────────────
# 🧠 TRANSFORMATION FUNCTIONS
# ───────────────────────────────────────────────────────────────

def get_top_recipients(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    df["award_amount"] = pd.to_numeric(df["Award Amount"], errors="coerce")
    df["recipient_name"] = df["Recipient Name"]
    return (
        df.groupby("recipient_name")["award_amount"]
        .sum()
        .nlargest(n)
        .reset_index()
        .rename(columns={"award_amount": "total_awarded"})
    )


def get_yearly_totals(df: pd.DataFrame) -> pd.DataFrame:
    df["start_date"] = pd.to_datetime(df["Start Date"], errors="coerce")
    df["year"] = df["start_date"].dt.year
    return (
        df.groupby("year")["Award Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Award Amount": "total_awarded"})
    )


def get_awards_by_state(df: pd.DataFrame) -> pd.DataFrame:
    df["state"] = df["Primary Place of Performance.state_code"]
    return (
        df.groupby("state")["Award Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Award Amount": "total_awarded"})
    )


def get_state_yearly_trends(df: pd.DataFrame) -> pd.DataFrame:
    df["state"] = df["Primary Place of Performance.state_code"]
    df["start_date"] = pd.to_datetime(df["Start Date"], errors="coerce")
    df["year"] = df["start_date"].dt.year
    return (
        df.groupby(["state", "year"])["Award Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Award Amount": "total_awarded"})
    )



# ───────────────────────────────────────────────────────────────
# 🔁 COMPOSITE FUNCTION (to plug into main_sam.py)
# ───────────────────────────────────────────────────────────────

def get_all_usaspending_insights(naics_code: str) -> dict[str, pd.DataFrame]:
    df = fetch_all_awards(naics_code)
    return {
        "top_recipients": get_top_recipients(df),
        "yearly_totals": get_yearly_totals(df),
        "awards_by_state": get_awards_by_state(df),
        "state_yearly_trends": get_state_yearly_trends(df),
    }



def push_insights_to_db(insights: dict[str, pd.DataFrame], naics_code: str, db_path: str = "bid_ally.db"):
    run_id = str(uuid.uuid4())
    run_timestamp = datetime.utcnow().isoformat()

    with sqlite3.connect(db_path) as conn:
        # Create the runs table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usaspending_runs (
                run_id TEXT PRIMARY KEY,
                naics_code TEXT,
                timestamp TEXT
            );
        """)
        conn.execute(
            "INSERT INTO usaspending_runs (run_id, naics_code, timestamp) VALUES (?, ?, ?)",
            (run_id, naics_code, run_timestamp)
        )
        print(f"✅ Inserted run metadata into usaspending_runs (run_id={run_id})")

        for table_name, df in insights.items():
            df["run_id"] = run_id
            db_table = f"usaspending_{table_name}"
            df.to_sql(db_table, conn, if_exists="append", index=False)
            print(f"✅ Appended {len(df)} rows to: {db_table} (run_id={run_id})")




if __name__ == "__main__":
    import sqlite3

    db_path = "bid_ally.db"

    # ─────────────────────────────────────────────────────────────
    # STEP 1: Clear out old schema (if exists)
    # ─────────────────────────────────────────────────────────────
    with sqlite3.connect(db_path) as conn:
        print("🧹 Dropping old tables...")
        conn.execute("DROP TABLE IF EXISTS usaspending_top_recipients;")
        conn.execute("DROP TABLE IF EXISTS usaspending_yearly_totals;")
        conn.execute("DROP TABLE IF EXISTS usaspending_awards_by_state;")
        conn.execute("DROP TABLE IF EXISTS usaspending_state_yearly_trends;")
        conn.execute("DROP TABLE IF EXISTS usaspending_runs;")
        print("✅ Old tables removed.")

    # ─────────────────────────────────────────────────────────────
    # STEP 2: Run a fresh ETL load using new schema
    # ─────────────────────────────────────────────────────────────
    naics_code = "621999"
    print(f"🚀 Fetching data for NAICS code: {naics_code}")
    insights = get_all_usaspending_insights(naics_code)

    for name, df in insights.items():
        df.to_csv(f"{name}.csv", index=False)

    push_insights_to_db(insights, naics_code)
    print("✅ ETL and schema setup complete.")


    

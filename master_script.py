# main_pipeline.py

import json
import pandas as pd
from main_sam import run_sam_pipeline
from main_eu import run_eu_pipeline

def normalize_eu_row(row):
    return {
        "source":       row["source"],
        "reference":    row["reference"],
        "title":        row["title"],
        "status":       row["status"],
        "solicitation": "",                     # Not available in EU
        "naics":        "",                     # Not available in EU
        "link":         row["url"],
        "tags":         row["tags"],
        "insights":     row["insights"],
        "swot":         row["swot"],
        "news_impacts": row["news_impacts"]
    }

def normalize_sam_row(row):
    return {
        "source":       row["source"],
        "reference":    row["sam_id"],
        "title":        row["title"],
        "status":       row["status"],
        "solicitation": row["solicitation"],
        "naics":        row["naics"],
        "link":         row["link"],
        "tags":         row["tags"],
        "insights":     row["insights"],
        "swot":         row["swot"],
        "news_impacts": row["news_impacts"]
    }

def run_combined_pipeline(out_json="combined_results_fire.json", out_csv="combined_results_fire.csv"):
    print("🚀 Running EU Tenders pipeline...")
    eu_data = run_eu_pipeline()
    print("🚀 Running SAM.gov pipeline...")
    sam_data = run_sam_pipeline()

    print("🔄 Normalizing EU + SAM data...")
    combined = [normalize_eu_row(row) for row in eu_data] + \
               [normalize_sam_row(row) for row in sam_data]

    print(f"✅ Total combined rows: {len(combined)}")

    # Save JSON
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    # Save CSV (flatten news_impacts)
    for row in combined:
        row["news_impacts"] = "; ".join(
            f"{impact['article_title']} – {impact['impact']}" for impact in row["news_impacts"]
        )

    df = pd.DataFrame(combined)
    df.to_csv(out_csv, index=False)

    print(f"✅ Outputs saved: {out_json}, {out_csv}")

if __name__ == "__main__":
    run_combined_pipeline()

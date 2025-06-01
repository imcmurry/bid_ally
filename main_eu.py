# eu_main.py
import json, time, pandas as pd, config
from eu_api_fetcher import fetch_all_pages
from rss_parser     import load_articles_from_db
from file_utils     import download_attachment, truncate_to_token_limit
from gpt_analysis   import (
    generate_insights, generate_swot_analysis,
    generate_solicitation_tags, generate_news_impact_paragraph,
)
from news_relevance import article_is_relevant
from file_utils import filter_attachments

def run_eu_pipeline(keywords=None, out_json="eu_results.json"):
    t0 = time.time()
    articles = load_articles_from_db()
    pages    = fetch_all_pages()
    if not pages:
        print("❌ EU API returned nothing.")
        return []

    rows, seen = [], set()

    for pg in pages:
        for item in pg.get("results", []):
            # --------------- basic filters ------------------
            if item.get("language") != "en":
                continue
            url = item.get("url", "")
            if url in seen:
                continue
            seen.add(url)

            # --------------- metadata -----------------------
            meta        = item.get("metadata", {})
            status_code = meta.get("status", [""])[0] if meta.get("status") else ""
            status_text = config.STATUS_MAPPING.get(status_code, "Unknown Status")

            # --------------- attachments --------------------
            downloads = []
            if status_text == "Open for Submission":
                cft_field = meta.get("cftDocuments", [])
                if cft_field and isinstance(cft_field, list):
                    raw = cft_field[0]

                    # raw may be a JSON string or already a dict
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw)
                        except json.JSONDecodeError:
                            raw = {}

                    if isinstance(raw, dict):
                        for doc in raw.get("cftDocuments", []):
                            fname = (
                                doc.get("hermesDocumentReferences", [{}])[0]
                                   .get("documentFileName", "")
                            )
                            if fname:
                                fp = download_attachment(item["reference"], fname)
                                if fp:
                                    downloads.append(fp)

                    downloads = filter_attachments(downloads)
            # --------------- GPT chain ----------------------
            insights = swot = ""
            tags     = []
            impacts  = []

            if downloads:
                content  = item["content"]
                desc     = meta.get("description", "")
                desc_b   = meta.get("descriptionByte", "")

                insights = generate_insights(content, desc, desc_b, downloads)
                swot     = generate_swot_analysis(content, desc, desc_b, insights, config.company_info)
                tags     = generate_solicitation_tags(content, desc, insights)

                sol_text = f"{content} {desc} {desc_b}"
                for art in articles:
                    art_txt = f"{art['title']} {art['description']} {art['content_encoded']}"
                    art_title = f"{art['title']}"
                    if article_is_relevant(art_title, art_txt, tags, sol_text):
                        impacts.append({
                            "article_title": art["title"],
                            "article_link": art["link"],
                            "impact": generate_news_impact_paragraph(
                                insights, art, config.company_info
                            )
                        })

            # --------------- collect row --------------------
            rows.append({
                "source"       : "EU Tenders",
                "reference"    : item["reference"],
                "url"          : url,
                "status"       : status_text,
                "title"        : meta.get("title", ""),
                "insights"     : insights,
                "swot"         : swot,
                "tags"         : "; ".join(tags),
                "news_impacts" : impacts,
            })
            print(f"EU – processed {len(rows)} rows…")

    # --------------- write output -------------------------
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"✅ EU pipeline finished ➜ {out_json}  "
          f"[{len(rows)} rows, {time.time()-t0:.1f}s]")
    return rows

# -----------------------------------------------------------------
if __name__ == "__main__":
    run_eu_pipeline()

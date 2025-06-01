# main_sam.py
import os
import json
import time
import config                                        # your existing config.py :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}
from sam_api_fetcher import fetch_sam_notices        # sam_api_fetcher.py
from rss_parser import load_articles_from_db         # rss_parser.py :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}
from gpt_analysis import (
    generate_insights,
    generate_swot_analysis,
    generate_solicitation_tags,
    generate_news_impact_paragraph
)                                                    # gpt_analysis.py :contentReference[oaicite:4]{index=4}&#8203;:contentReference[oaicite:5]{index=5}
from news_relevance import article_is_relevant       # news_relevance.py :contentReference[oaicite:6]{index=6}&#8203;:contentReference[oaicite:7]{index=7}
from file_utils import filter_attachments

def run_sam_pipeline(
    *,
    out_json: str = "sam_results.json",
    notice_cache_file: str = "guam_notice_cache.json",
    processed_cache_file: str = "processed_sam_cache.json",
) -> list[dict]:
    """
    Pull SAM.gov notices, analyse them, and write results to disk **incrementally** so
    the script can be interrupted and safely restarted without repeating work.
    All GPT calls are wrapped in a MAX_GPT_RETRIES guard to stop infinite loops.
    """
    import os, json, time, traceback

    MAX_GPT_RETRIES = 1      # per notice for insights / swot / tags
    t0 = time.time()

    # ------------------------------------------------------------------ 1. Load notices
    if os.path.exists(notice_cache_file):
        with open(notice_cache_file, "r", encoding="utf-8") as f:
            notices = json.load(f)
        print(f"📁 Loaded {len(notices)} notices from {notice_cache_file}")
    else:
        print("📡 Fetching notices from SAM API …")
        notices = fetch_sam_notices(config.SAM_SEARCH_KEYWORDS)
        with open(notice_cache_file, "w", encoding="utf-8") as f:
            json.dump(notices, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved raw notices to {notice_cache_file}")

    # ------------------------------------------------------------------ 2. Load processed‑row cache
    processed_cache: dict[str, dict] = {}
    if os.path.exists(processed_cache_file):
        with open(processed_cache_file, "r", encoding="utf-8") as f:
            processed_cache = json.load(f)

    # quick helper to persist after every notice
    def _flush_cache():
        with open(processed_cache_file, "w", encoding="utf-8") as f_cache:
            json.dump(processed_cache, f_cache, indent=2, ensure_ascii=False)

    rows: list[dict] = []
    articles = load_articles_from_db()

    # ------------------------------------------------------------------ 3. Main loop
    for n_idx, notice in enumerate(notices, 1):
        notice_id = notice.get("sam_id") or f"idx_{n_idx}"
        if notice_id in processed_cache:
            rows.append(processed_cache[notice_id])
            print(f"🔄  Skipping (cached) {notice_id}")
            continue
        
        
        print(f"🚀 Processing {notice_id}  [{n_idx}/{len(notices)}]")
        try:
            ######################################################## attachments filter
            desc = notice.get("description", "")
            raw_attachments = notice.get("attachments", [])
            

            # Now we only keep the small or “RFP/SOW/…” attachments
            attachments = filter_attachments(raw_attachments)

            ######################################################## GPT‑calls with retry
            def _safe_call(fn, *a, **kw):
                for i in range(1, MAX_GPT_RETRIES + 1):
                    try:
                        return fn(*a, **kw)
                    except Exception as e:
                        print(f"⚠️ {i}/{MAX_GPT_RETRIES} {fn.__name__} failed: {e}")
                        if i == MAX_GPT_RETRIES:
                            return f"[ERROR after {MAX_GPT_RETRIES} tries]"
                        time.sleep(2)

            content_for_gpt = desc if not attachments else (
                notice.get("attachments_text", "") or desc
            )

            insights = _safe_call(
                generate_insights,
                content_for_gpt, desc, "", attachments,
            )
            swot = _safe_call(
                generate_swot_analysis,
                content_for_gpt, desc, "", insights, config.company_info,
            )
            tags = _safe_call(
                generate_solicitation_tags,
                content_for_gpt, desc, insights,
            )

            ######################################################## news impacts
            impacts = []
            if isinstance(tags, list):
                tag_text = "; ".join(tags)
                sol_text = f"{content_for_gpt} {desc}"
                for art in articles:
                    art_txt = f"{art['title']} {art['description']} {art.get('content_encoded','')}"
                    if article_is_relevant(art["title"], art_txt, tags, sol_text):
                        impacts.append({
                            "article_title": art["title"],
                            "article_link": art["link"],
                            "impact": _safe_call(
                                generate_news_impact_paragraph,
                                insights, art, config.company_info
                            ),
                        })
            else:
                tag_text = tags  # already an error string

            ######################################################## assemble row
            row = {
                "source":       "SAM.gov",
                "sam_id":       notice_id,
                "solicitation": notice.get("solicitation"),
                "link":         notice.get("link"),
                "naics":        notice.get("naics"),
                "status":       notice.get("status"),
                "title":        notice.get("title"),
                "insights":     insights,
                "swot":         swot,
                "tags":         tag_text,
                "news_impacts": impacts,
            }
            rows.append(row)
            processed_cache[notice_id] = row
            _flush_cache()
            print(f"✅ Finished {notice_id} (cache size {len(processed_cache)})")

        except Exception as e:  # catch EVERYTHING so the loop continues
            traceback.print_exc()
            print(f"❌ Fatal error on notice {notice_id}: {e}")
            processed_cache[notice_id] = {"error": str(e)}
            _flush_cache()
            continue

    # ------------------------------------------------------------------ 4. final output
    with open(out_json, "w", encoding="utf-8") as f_out:
        json.dump(rows, f_out, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print(f"🏁 SAM pipeline done → {out_json}  ({len(rows)} rows, {elapsed:.1f}s)")
    return rows





if __name__ == "__main__":
    run_sam_pipeline()

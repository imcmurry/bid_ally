# sam_api_fetcher.py
import os
import time
import requests
import config
from file_utils import download_attachment_sam

import fitz   # PyMuPDF
import docx
import pandas as pd


# ----------------------------
# Query helpers
# ----------------------------
def _quote_if_needed(s: str) -> str:
    s = str(s).strip()
    # Wrap in quotes if there is whitespace or parentheses to preserve grouping
    if any(ch.isspace() for ch in s) or "(" in s or ")" in s:
        return f'"{s}"'
    return s

def _build_query_and_mode(passed_keywords: list[str] | None = None) -> tuple[str, str]:
    """
    Build the SAM.gov query string and return (query, q_mode).

    If config.SAM_REGIONS exists and is non-empty, we build:
        (r1 OR r2 OR ...) AND (k1 OR k2 OR ...)
      and force qMode=SEARCH_EDITOR.

    Otherwise, we fall back to the first keyword and qMode=EXACT
    (or join all keywords with space, same as historical behavior).
    """
    regions = getattr(config, "SAM_REGIONS", []) or []
    keywords = getattr(config, "SAM_SEARCH_KEYWORDS", []) or (passed_keywords or [])

    # Clean/quote
    regions = [ _quote_if_needed(r) for r in regions if str(r).strip() ]
    keywords = [ _quote_if_needed(k) for k in keywords if str(k).strip() ]

    if regions and keywords:
        region_expr  = " OR ".join(regions)
        keyword_expr = " OR ".join(keywords)
        query = f"({region_expr}) AND ({keyword_expr})"
        return query, "SEARCH_EDITOR"

    # Fallback: keep legacy behavior (simple keywords via EXACT mode)
    if keywords:
        # With EXACT mode SAM will treat q as a single term; if you pass multiple,
        # SAM interprets it more like space-separated tokens — stick to first term
        # to match previous logic, or join with space if you prefer.
        query = keywords[0]
        return query, "EXACT"

    # Final fallback: empty query (should not happen in normal use)
    return "", "EXACT"


# ----------------------------
# API calls
# ----------------------------
def get_search_results(query: str, page: int = 0, size: int = 100, q_mode: str = "EXACT"):
    """Fetch a page of SAM.gov search results."""
    base_url = "https://sam.gov/api/prod/sgs/v1/search/"
    params = {
        "random": int(time.time() * 1000),
        "index": "_all",
        "page": page,
        "size": size,
        "mode": "search",
        "sort": "-modifiedDate",
        "mfe": "true",
        "q": query,
        "qMode": q_mode,          # EXACT or SEARCH_EDITOR
        "is_active": "true",
    }
    r = requests.get(base_url, params=params)
    if r.status_code == 200:
        return r.json()
    print(f"Error fetching search results ({r.status_code}) for q={query!r} qMode={q_mode}")
    return None


def get_bid_details(bid_id):
    """Fetch the full opportunity record for a given SAM ID, with a fallback if the main endpoint fails."""
    url_primary = f"https://sam.gov/api/prod/opps/v2/opportunities/{bid_id}?random={int(time.time()*1000)}"
    r = requests.get(url_primary)

    if r.status_code == 200:
        return r.json()
    elif r.status_code in [400, 401]:
        print(f"⚠️ Primary endpoint failed for ID {bid_id} with {r.status_code}. Trying fallback endpoint...")
        url_fallback = f"https://sam.gov/api/pro/fa/v1/programs/{bid_id}?random={int(time.time()*1000)}"
        r_fallback = requests.get(url_fallback)
        if r_fallback.status_code == 200:
            return r_fallback.json()
        else:
            print(f"❌ Fallback also failed for ID {bid_id}: {r_fallback.status_code}")
    else:
        print(f"❌ Error fetching bid details for ID {bid_id}: {r.status_code}")

    return None


def get_attachments(bid_id):
    """List all attachments (PDF/DOCX/XLSX) for an opportunity."""
    url = f"https://sam.gov/api/prod/opps/v3/opportunities/{bid_id}/resources"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    print(f"Error fetching attachments for ID {bid_id}: {r.status_code}")
    return None


def parse_attachment(path):
    """Extract text from PDF, DOCX, or XLSX attachments."""
    if path.lower().endswith(".pdf"):
        with fitz.open(path) as doc:
            return "\n".join(p.get_text("text") for p in doc)
    elif path.lower().endswith(".docx"):
        docx_doc = docx.Document(path)
        return "\n".join(p.text for p in docx_doc.paragraphs)
    elif path.lower().endswith((".xls", ".xlsx")):
        try:
            sheets = pd.read_excel(path, sheet_name=None)
            return "\n".join(df.to_string() for df in sheets.values())
        except Exception as e:
            return f"[Error reading spreadsheet: {e}]"
    else:
        return "[Unsupported file type]"


def fetch_sam_notices(keywords, attachments_dir=config.ATTACHMENTS_DIR):
    """
    Page through SAM.gov search results for the built query,
    download & parse attachments, and return a list of dicts:
      {
        sam_id, title, solicitation, naics, status,
        description, attachments (paths list), attachments_text
      }
    """
    os.makedirs(attachments_dir, exist_ok=True)
    notices = []
    page_size = 100  # Full page

    # NEW: build the single advanced query (regions OR …) AND (keywords OR …)
    query, q_mode = _build_query_and_mode(passed_keywords=keywords)
    if not query:
        print("No query could be built from config/inputs; aborting.")
        return notices

    page = 0
    total_pages = 1  # Will update based on first API response

    while page < total_pages:
        resp = get_search_results(query, page=page, size=page_size, q_mode=q_mode)
        if not (resp and "_embedded" in resp and "results" in resp["_embedded"]):
            break

        results = resp["_embedded"]["results"]
        page_info = resp.get("page", {})
        total_pages = page_info.get("totalPages", total_pages)

        if page == 0:
            print(f"🔍 Query: [{q_mode}] {query!r} — Total pages: {total_pages}")

        for res in results:
            bid_id = res.get("_id")
            if not bid_id:
                continue

            bid = get_bid_details(bid_id)
            if not bid:
                continue

            data2 = bid.get("data2", {})
            title = data2.get("title", "N/A")
            naics = data2.get("naics", [{}])[0].get("code", "N/A")
            sol_number = data2.get("solicitationNumber", "N/A")
            status = bid.get("status", {}).get("value", "N/A")
            description = (
                bid.get("description")[0]["body"]
                if bid.get("description") else "N/A"
            )
            print(f"Title: {title}")

            # --- attachments ---
            att_json = get_attachments(bid_id)
            att_paths = []
            att_text = ""
            if att_json and "_embedded" in att_json:
                for wrap in att_json["_embedded"].get("opportunityAttachmentList", []):
                    for att in wrap.get("attachments", []):
                        rid = att.get("resourceId")
                        name = att.get("name")
                        if rid and name:
                            local = download_attachment_sam(rid, name)
                            if local:
                                att_paths.append(local)
                                att_text += f"\n[Attachment: {name}]\n{parse_attachment(local)}\n"

            notices.append({
                "sam_id": bid_id,
                "title": title,
                "solicitation": sol_number,
                "naics": naics,
                "status": status,
                "description": description,
                "link": f"https://sam.gov/opp/{bid_id}/view",
                "attachments": att_paths,
                "attachments_text": att_text
            })

        print(f"🔹 Collected {len(notices)} notices so far...")

        if len(results) < page_size:
            break  # Last page reached

        page += 1
        time.sleep(0.3)

    return notices

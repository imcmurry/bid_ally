# sam_api_fetcher.py
import time
import os
import requests
import config                               # your existing config.py :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}
from file_utils import download_attachment_sam  # your existing file_utils.py :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}

import fitz   # PyMuPDF
import docx
import pandas as pd

def get_search_results(keyword, page=0, size=100):
    """Fetch a page of SAM.gov search results."""
    url = (
        f"https://sam.gov/api/prod/sgs/v1/search/"
        f"?random={int(time.time()*1000)}"
        f"&index=_all&page={page}&size={size}"
        f"&mode=search&sort=-modifiedDate"
        f"&mfe=true&q={keyword}&qMode=EXACT&is_active=true"
    )
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    print(f"Error fetching search results: {r.status_code}")
    return None

import requests
import time

def get_bid_details(bid_id):
    """Fetch the full opportunity record for a given SAM ID, with a fallback if the main endpoint fails."""
    # Primary endpoint
    url_primary = f"https://sam.gov/api/prod/opps/v2/opportunities/{bid_id}?random={int(time.time()*1000)}"
    r = requests.get(url_primary)
    
    if r.status_code == 200:
        return r.json()
    elif r.status_code in [400, 401]:
        print(f"⚠️ Primary endpoint failed for ID {bid_id} with {r.status_code}. Trying fallback endpoint...")

        # Fallback endpoint
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
    For each keyword, page through SAM.gov search results,
    download & parse all attachments, and return a list of dicts:
      {
        sam_id, title, solicitation, naics, status,
        description, attachments (paths list), attachments_text
      }
    """
    os.makedirs(attachments_dir, exist_ok=True)
    notices = []
    page_size = 100  # Full page

    for kw in keywords:
        page = 0
        total_pages = 1  # Will update based on first API response

        while page < total_pages:
            resp = get_search_results(kw, page=page, size=page_size)
            if not (resp and "_embedded" in resp and "results" in resp["_embedded"]):
                break

            results = resp["_embedded"]["results"]
            page_info = resp.get("page", {})
            total_pages = page_info.get("totalPages", total_pages)

            if page == 0:
                print(f"🔍 Keyword: '{kw}' — Total pages: {total_pages}")

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



    

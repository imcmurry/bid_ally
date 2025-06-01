# single_solicitation.py
import json
import time

import re
from urllib.parse import urlparse, parse_qs

import config
from file_utils import (
    download_attachment_sam,
    download_attachment,
    filter_attachments,
    extract_text_from_files
)
from sam_api_fetcher import get_bid_details, get_attachments as sam_get_attachments
from eu_api_fetcher import fetch_all_pages
from gpt_analysis import (
    generate_insights,
    generate_swot_analysis,
    generate_solicitation_tags,
    generate_news_impact_paragraph
)
from rss_parser import load_articles_from_db
from news_relevance import article_is_relevant


# ─────────────────────────────────────────────────────────────────────────────
# 1) Helpers to detect and parse SAM vs EU URLs
# ─────────────────────────────────────────────────────────────────────────────

def _is_sam_url(url: str) -> bool:
    return "sam.gov" in url and "/opp/" in url

def _is_eu_url(url: str) -> bool:
    return "reference=" in url

def _is_eu_guid_url(url: str) -> bool:
    """
    Matches URLs like:
      https://…/tender‐details/<GUID>‐CN?…
    """
    return bool(re.search(r"/tender-details/[0-9a-fA-F\-]+-CN", url))

def _extract_eu_guid_reference(url: str) -> str:
    """
    Given:
      https://…/tender-details/92aecb3b-f0e2-421b-9f84-5afdbd902ecf-CN?…
    returns:
      "92aecb3b-f0e2-421b-9f84-5afdbd902ecf-CN"
    """
    parsed = urlparse(url)
    return parsed.path.rstrip("/").split("/")[-1]


def _parse_eu_reference(url: str) -> str | None:
    """
    Given a URL containing "?reference=<value>", returns that <value>.
    e.g. “?reference=92aecb3b-f0e2-421b-9f84-5afdbd902ecf-CN”.
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    ref_list = qs.get("reference") or qs.get("REF") or qs.get("Reference")
    if isinstance(ref_list, list) and len(ref_list) > 0:
        return ref_list[0]
    return None

def _parse_sam_id(url: str) -> str | None:
    """
    Extracts the opportunity ID from a SAM.gov URL of the form:
      https://sam.gov/opp/<SAM_ID>/view
    Returns the SAM_ID (e.g. “ABC123”) or None if not found.
    """
    m = re.search(r"/opp/([^/]+)/view", url)
    return m.group(1) if m else None
# ────────────────────────────────────────────────────────────────────────────
def process_single_url(url: str) -> dict:
    url = url.strip()

    # 1) SAM link?
    if _is_sam_url(url):
        return _process_sam_link(url)

    # 2) GUID‐style EU link ("/tender-details/<GUID>-CN?…")
    elif _is_eu_guid_url(url):
        ref_guid = _extract_eu_guid_reference(url)  # e.g. "92aecb3b-…-CN"
        eu_ref_url = (
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
            f"screen/opportunities/call-details?reference={ref_guid}"
        )
        return _process_eu_link(eu_ref_url)

    # 3) Already‐formatted "call-details?reference=<…>" link
    elif _is_eu_url(url):
        return _process_eu_link(url)

    # 4) Not recognized
    else:
        raise ValueError(f"URL does not appear to be a SAM or EU Tenders opportunity: {url}")

# ─────────────────────────────────────────────────────────────────────────────
# 2) Core logic to process a SAM.gov link
# ─────────────────────────────────────────────────────────────────────────────

def _process_sam_link(url: str) -> dict:
    """
    For a given SAM.gov opportunity URL, fetch that one bid’s metadata,
    fetch & filter attachments, then call GPT‐analysis steps.
    Returns a dict that mirrors one row of your SAM pipeline output.
    """
    # 2.1) Extract the SAM ID from the URL
    sam_id = _parse_sam_id(url)
    if not sam_id:
        raise ValueError(f"Could not parse SAM ID from URL: {url}")

    # 2.2) Fetch full opportunity record (metadata + attachments list)
    bid = get_bid_details(sam_id)
    if not bid:
        raise RuntimeError(f"get_bid_details({sam_id}) returned nothing.")

    data2 = bid.get("data2", {})
    title = data2.get("title", "N/A")
    naics_code = data2.get("naics", [{}])[0].get("code", "N/A")
    solicitation_number = data2.get("solicitationNumber", "N/A")
    status = bid.get("status", {}).get("value", "N/A")
    description = ""
    if bid.get("description"):
        # SAM returns description as a list of dicts; take the first body
        try:
            description = bid["description"][0].get("body", "") or ""
        except Exception:
            description = ""

    # 2.3) Download attachments
    attachment_paths: list[str] = []
    att_json = sam_get_attachments(sam_id)
    if att_json and "_embedded" in att_json:
        for wrap in att_json["_embedded"].get("opportunityAttachmentList", []):
            for att in wrap.get("attachments", []):
                resource_id = att.get("resourceId")
                name = att.get("name")
                if resource_id and name:
                    local_path = download_attachment_sam(resource_id, name)
                    if local_path:
                        attachment_paths.append(local_path)

    # 2.4) Filter attachments (≤ 1 MB or name contains “rfp”/“proposal”/“SOW”, etc.)
    attachments = filter_attachments(attachment_paths)

    # 2.5) Extract text from each PDF for GPT inputs
    attachments_text = ""
    if attachments:
        attachments_text = extract_text_from_files(attachments)

    # 2.6) Build the "content_for_gpt" exactly as your SAM pipeline did:
    content_for_gpt = attachments_text if attachments else description

    # 2.7) Run GPT steps with safe‐retry wrapper (reuse your existing logic for SAM)
    #      We’ll inline a minimal “retry‐once” guard, just like main_sam.py did.
    MAX_GPT_RETRIES = 1

    def _safe_call(fn, *args, **kwargs):
        for i in range(1, MAX_GPT_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                print(f"⚠️ {i}/{MAX_GPT_RETRIES} {fn.__name__} failed: {e}")
                if i == MAX_GPT_RETRIES:
                    return f"[ERROR after {MAX_GPT_RETRIES} tries: {e}]"
                time.sleep(2)

    insights = _safe_call(generate_insights,
                          content_for_gpt,
                          description,
                          "",     # SAM’s code passed empty string for description_byte
                          attachments)

    swot = _safe_call(generate_swot_analysis,
                      content_for_gpt,
                      description,
                      "",
                      insights,
                      config.company_info)

    tags = _safe_call(generate_solicitation_tags,
                      content_for_gpt,
                      description,
                      insights)

    # 2.8) Compute related‐news impacts exactly as SAM pipeline did
    news_impacts: list[dict] = []
    if isinstance(tags, list):
        # Load all saved RSS articles once (this is identical to run_sam_pipeline)
        articles = load_articles_from_db()
        sol_text = f"{content_for_gpt} {description}"
        for art in articles:
            art_txt = f"{art['title']} {art['description']} {art.get('content_encoded','')}"
            if article_is_relevant(art["title"], art_txt, tags, sol_text):
                impact_paragraph = _safe_call(
                    generate_news_impact_paragraph,
                    insights,
                    art,
                    config.company_info
                )
                news_impacts.append({
                    "article_title": art["title"],
                    "article_link": art["link"],
                    "impact": impact_paragraph
                })
    else:
        # If tags is a string (error), skip news impacts
        news_impacts = []

    # 2.9) Return exactly the same keys your SAM‐pipeline row uses
    return {
        "source":       "SAM.gov",
        "reference":    sam_id,
        "title":        title,
        "status":       status,
        "solicitation": solicitation_number,
        "naics":        naics_code,
        "link":         url,
        "insights":     insights,
        "swot":         swot,
        "tags":         tags if isinstance(tags, list) else [tags],
        "news_impacts": news_impacts
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3) Core logic to process an EU Tenders link
# ─────────────────────────────────────────────────────────────────────────────

def _process_eu_link(url: str) -> dict:
    """
    For a given EU Tenders ‘tender‐details.html?reference=XXXXX’ URL,
    find that one item via the API, fetch attachments, run GPT steps.
    Returns a dict matching one EU pipeline row.
    """
    # 3.1) Extract the reference ID from the URL
    reference = _parse_eu_reference(url)
    if not reference:
        raise ValueError(f"Could not parse EU reference from URL: {url}")

    # 3.2) Search the EU API for that reference alone.
    #      We’ll pass search_text=f'"{reference}"' so that the API
    #      hopefully returns exactly that tender on some page.
    pages = fetch_all_pages(search_text=f'"{reference}"')
    if not pages:
        raise RuntimeError(f"EU API returned no pages when searching '{reference}'.")

    item = None
    for pg in pages:
        for it in pg.get("results", []):
            if it.get("reference") == reference:
                item = it
                break
        if item:
            break

    if not item:
        raise RuntimeError(f"Could not find any item with reference={reference} in EU results.")

    # 3.3) Pull metadata fields
    meta = item.get("metadata", {})
    status_code = ""
    if meta.get("status"):
        status_code = meta["status"][0]
    status = config.STATUS_MAPPING.get(status_code, "Unknown Status")
    title = meta.get("title", "")

    content = item.get("content", "")
    description = meta.get("description", "") or ""
    description_byte = meta.get("descriptionByte", "") or ""

    # 3.4) Download all attachments exactly as run_eu_pipeline did:
    attachment_paths: list[str] = []
    if status == "Open for Submission":
        cft_field = meta.get("cftDocuments", [])
        if cft_field and isinstance(cft_field, list):
            raw = cft_field[0]
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
                            attachment_paths.append(fp)

    # 3.5) Filter attachments
    attachments = filter_attachments(attachment_paths)

    # 3.6) Extract text from PDFs
    attachments_text = ""
    if attachments:
        attachments_text = extract_text_from_files(attachments)

    # 3.7) Choose content_for_gpt (exact same logic as EU pipeline)
    content_for_gpt = attachments_text if attachments else f"{content} {description} {description_byte}"

    # 3.8) Run GPT calls with a minimal retry guard
    MAX_GPT_RETRIES = 3

    def _safe_call(fn, *args, **kwargs):
        for i in range(1, MAX_GPT_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                print(f"⚠️ {i}/{MAX_GPT_RETRIES} {fn.__name__} failed: {e}")
                if i == MAX_GPT_RETRIES:
                    return f"[ERROR after {MAX_GPT_RETRIES} tries: {e}]"
                time.sleep(2)

    insights = _safe_call(
        generate_insights,
        content_for_gpt,
        description,
        description_byte,
        attachments
    )

    swot = _safe_call(
        generate_swot_analysis,
        content_for_gpt,
        description,
        description_byte,
        insights,
        config.company_info
    )

    tags = _safe_call(
        generate_solicitation_tags,
        content_for_gpt,
        description,
        insights
    )

    # 3.9) Compute news impacts (reuse same logic)
    news_impacts: list[dict] = []
    if isinstance(tags, list):
        articles = load_articles_from_db()
        sol_text = f"{content_for_gpt} {description} {description_byte}"
        for art in articles:
            art_txt = f"{art['title']} {art['description']} {art['content_encoded']}"
            if article_is_relevant(art["title"], art_txt, tags, sol_text):
                impact_paragraph = _safe_call(
                    generate_news_impact_paragraph,
                    insights,
                    art,
                    config.company_info
                )
                news_impacts.append({
                    "article_title": art["title"],
                    "article_link": art["link"],
                    "impact": impact_paragraph
                })
    else:
        news_impacts = []

    # 3.10) Return a dict matching your EU pipeline’s row schema
    return {
        "source":       "EU Tenders",
        "reference":    reference,
        "url":          url,
        "status":       status,
        "title":        title,
        "insights":     insights,
        "swot":         swot,
        "tags":         tags if isinstance(tags, list) else [tags],
        "news_impacts": news_impacts
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4) Single entry‐point: inspect URL, dispatch to SAM or EU
# ─────────────────────────────────────────────────────────────────────────────

def process_single_url(url: str) -> dict:
    """
    Detects whether `url` is a SAM.gov link or EU Tenders link.
    Then calls _process_sam_link(url) or _process_eu_link(url).
    Returns a single‐row dict ready for downstream display/storage.
    """
    url = url.strip()
    if _is_sam_url(url):
        return _process_sam_link(url)
    elif _is_eu_url(url):
        return _process_eu_link(url)
    else:
        raise ValueError(f"URL does not appear to be a SAM or EU Tenders opportunity: {url}")


# ─────────────────────────────────────────────────────────────────────────────
# 5) (Optional) If you ever want to run this module standalone for testing:
if __name__ == "__main__":
    test_url = input("Enter a SAM.gov or EU Tenders URL: ").strip()
    try:
        row = process_single_url(test_url)
        print(json.dumps(row, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Error: {e}")

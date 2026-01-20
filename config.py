# config.py

from dotenv import load_dotenv
import os
import openai
from pathlib import Path

load_dotenv()

# ------------------------------------------------------------------------------
# 1) OPENAI SETTINGS
# ------------------------------------------------------------------------------
# If you prefer not to hard-code, load from environment or .env:
#    from dotenv import load_dotenv
#    load_dotenv()
#    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# For demo, we keep your existing key here (NOT recommended for production).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai.api_key = OPENAI_API_KEY

# If you only have a project‐scoped key, you must also specify the project ID (or organization ID).
# Example (replace PROJECT_ID with your actual Project ID from the OpenAI dashboard):
openai.api_project = "proj_cyHvUEE26hU3JeOc9juN6Yoh"

# The GPT model used for ChatCompletion calls (you have "gpt-4o" in your script)
GPT_MODEL_CHAT = "gpt-4o"

# The model for embeddings (used in article relevance checks)
GPT_MODEL_EMBEDDING = "text-embedding-3-small"


# ------------------------------------------------------------------------------
# 2) COMPANY / TEAM DETAILS
# ------------------------------------------------------------------------------
company_info = {
    "company_name": "Bridger Aerospace",
    "core_competencies": (
        "Bridger Aerospace is a U.S.-based aerial firefighting and special-mission aviation company "
        "headquartered in Montana. The company specializes in wildfire suppression, disaster response, "
        "and emergency aviation operations, with a core capability centered on amphibious water-scooping "
        "aircraft operations. Bridger operates a dedicated fleet of CL-415EAF 'Super Scooper' aircraft, "
        "designed for rapid, low-altitude water delivery directly onto active fires. Capabilities include "
        "high-tempo aerial firefighting, precision water drops, mission planning, airspace coordination, "
        "and deployment of aviation assets in permissive, non-combat environments supporting civil and "
        "government authorities."
    ),
    "past_performance": (
        "Bridger Aerospace supports U.S. wildfire response efforts through federal task orders and seasonal "
        "mobilizations, including operations under agencies such as the U.S. Forest Service. The company "
        "has demonstrated sustained operational performance conducting repeated, high-frequency water-drop "
        "missions during active wildfire seasons. Past performance emphasizes real-world execution of "
        "aerial firefighting operations, coordination with federal and state incident command structures, "
        "and reliable delivery of time-critical aviation services rather than one-time or experimental missions."
    ),
    "unique_strengths": (
        "Purpose-built fleet of amphibious CL-415EAF aircraft optimized for rapid water scooping from nearby "
        "lakes, rivers, and coastal environments, enabling high sortie rates without reliance on fixed tanker bases. "
        "Operational expertise in low-altitude, precision aerial delivery for structure defense, infrastructure "
        "protection, and urban-interface fire suppression. Well positioned for humanitarian assistance, disaster "
        "relief, and installation resilience missions where speed, repeatability, and reduced logistics footprint "
        "are critical. Commercial operator model aligns with government contracting approaches that favor scalable, "
        "contracted aviation capabilities in permissive operating environments."
    ),
}







# ------------------------------------------------------------------------------
# 3) EU API SETTINGS
# ------------------------------------------------------------------------------
# The 'SEDIA' key used in your code
EU_API_KEY = "SEDIA"

# Base URL and parameters
EU_BASE_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
EU_SEARCH_TEXT = '"guam"'   # You had search_text='"medical"'
EU_PAGE_SIZE = 100

# Common request headers
REQUEST_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json"
}

# Status mapping from the metadata status code to a human-readable status
STATUS_MAPPING = {
    "31094503": "Closed",
    "31094501": "Forthcoming",
    "31094502": "Open for Submission"
}


# ------------------------------------------------------------------------------
# 4) FILE / DIRECTORY SETTINGS
# ------------------------------------------------------------------------------
ATTACHMENTS_DIR = "attachments"
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

# Output JSON files
OUTPUT_JSON = "extracted_data_w_news_higher_threshold.json"
RAW_OUTPUT_JSON = "raw_api_data_files.json"


# ------------------------------------------------------------------------------
# 5) RSS / XML SETTINGS
# ------------------------------------------------------------------------------
# Database name
DB_NAME = "rss_data7.db"

# Namespace used for <content:encoded> in the RSS feeds
XML_NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/"
}


# ------------------------------------------------------------------------------
# 6) OTHER CONSTANTS / THRESHOLDS
# ------------------------------------------------------------------------------
# Cosine similarity threshold for determining if an article is relevant
RELEVANCE_THRESHOLD = 0.745

# Max characters to keep when truncating text for GPT prompts
MAX_CHARS = 4000
GPT_MODEL_CHAT = "gpt-4.1-mini"         # or "gpt-4" / "gpt-3.5-turbo" depending on your usage
GPT_MAX_INPUT_TOKENS = 123000  

# ------------------------------------------------------------------------------
# 7) OPTIONAL: MODEL TEMPERATURES, TOKENS, ETC.
# ------------------------------------------------------------------------------
# Control GPT settings more dynamically
GPT_TEMPERATURE = 0.7
GPT_MAX_TOKENS = 1024


#8) SAM SETTINGS
SAM_SEARCH_KEYWORDS = ["Philippines Aeromedical"]
SAM_REGIONS = []

ROOT = Path(__file__).parent
DATA_PATH = ROOT / "combined_results_fire.json"

DB_PATH = ROOT / "bid_ally.db"

PERPLEXITY_KEY = "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"
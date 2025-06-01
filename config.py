# config.py

from dotenv import load_dotenv
import os
import openai

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
GPT_MODEL_EMBEDDING = "text-embedding-ada-002"


# ------------------------------------------------------------------------------
# 2) COMPANY / TEAM DETAILS
# ------------------------------------------------------------------------------
company_info = {
    "company_name": "Acuity International",
    "core_competencies": (
        "Acuity International delivers integrated mission solutions and global health services, "
        "specializing in program and construction management, environmental remediation, base operations, "
        "security services, occupational health, medical services, emergency and disaster response, and civil services. "
        "Their expertise supports federal, state, and local governments in building safe, secure, healthy, and thriving communities worldwide."
    ),
    "past_performance": (
        "With over 20 years of experience, Acuity International has a proven track record in providing rapid deployment, "
        "emergency response, and comprehensive support services in challenging environments. "
        "Their past performance includes successful delivery of medical services, disaster recovery, and base operations support "
        "for various government agencies and international missions."
    ),
    "unique_strengths": (
        "Acuity International's unique strengths lie in their ability to integrate advanced technology with expert talent "
        "to deliver tailored solutions in complex environments. Their commitment to compliance, quality management, "
        "and rapid response capabilities positions them as a trusted partner for critical missions globally."
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
DB_NAME = "rss_data6.db"

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
SAM_SEARCH_KEYWORDS = [
    "guam"
    
]
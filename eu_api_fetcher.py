# eu_api_fetcher.py
import requests
import time
import config


def fetch_page(page_number: int, search_text: str = None) -> dict:
    """
    Fetches a single page of results from the EU Commission API.
    
    :param page_number: Which page to fetch (1-based index).
    :param search_text: An optional query string (e.g. '"medical"').
                        If None, defaults to config.EU_SEARCH_TEXT.
    :return: A dictionary with JSON data for that page, or an empty dict if an error occurs.
    """
    if search_text is None:
        search_text = config.EU_SEARCH_TEXT

    params = {
        "apiKey": config.EU_API_KEY,
        "text": search_text,
        "pageSize": config.EU_PAGE_SIZE,
        "pageNumber": page_number
    }

    try:
        response = requests.post(config.EU_BASE_URL, headers=config.REQUEST_HEADERS, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error on page {page_number}: {response.status_code} - {response.text}")
            return {}
    except requests.RequestException as e:
        print(f"❌ Request error on page {page_number}: {e}")
        return {}


def fetch_all_pages(search_text: str = None, delay_seconds: float = 1.0) -> list:
    """
    Fetches all pages of EU solicitations for the given search text,
    handling pagination automatically.

    :param search_text: Query string (e.g. '"medical"'), defaults to config.EU_SEARCH_TEXT.
    :param delay_seconds: How many seconds to wait between page fetches to avoid rate-limits.
    :return: A list of JSON/dict objects, one per page.
    """
    # Fetch the first page to see how many results/pages exist
    first_page_data = fetch_page(1, search_text=search_text)
    if not first_page_data:
        print("❌ No data returned from first page.")
        return []

    # Calculate total pages
    total_results = first_page_data.get("totalResults", 0)
    total_pages = (total_results // config.EU_PAGE_SIZE) + (1 if total_results % config.EU_PAGE_SIZE != 0 else 0)
    print(f"📊 Total Results Found: {total_results}")
    print(f"📄 Total Pages to Scrape: {total_pages}")

    # Store data for all pages
    all_pages_data = [first_page_data]

    # Fetch subsequent pages
    for page_number in range(2, total_pages + 1):
        print(f"🔄 Fetching page {page_number}...")
        page_data = fetch_page(page_number, search_text=search_text)
        if page_data:
            all_pages_data.append(page_data)

        # Wait between requests to avoid hammering the API
        time.sleep(delay_seconds)

    return all_pages_data

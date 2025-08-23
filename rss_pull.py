# rss_pull.py

import sqlite3
import requests
import feedparser
import time
import xml.etree.ElementTree as ET
import datetime
from time import mktime

# Define RSS feed categories and base URL
BASE_URL = "https://www.defensenews.com/arc/outboundfeeds/rss"
SECTION_SLUGS = [
    "", "air", "land", "naval", "pentagon", "congress", "space",
    "training-sim", "unmanned", "global", "industry", "interviews", "opinion"
]

########################################################################
# SQLite DB Setup
########################################################################

def setup_database(db_name="rss_data7.db"):
    conn = sqlite3.connect(db_name)
    cur = conn.cursor()

    # If table doesn't exist, create it with proper columns
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rss_articles'")
    if not cur.fetchone():
        cur.execute("""
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_name TEXT,
            title TEXT,
            link TEXT,
            pub_date DATETIME,
            description TEXT,
            guid TEXT,
            categories TEXT,
            content_encoded TEXT
        );
        """)
        conn.commit()

    return conn

########################################################################
# Insert Article into DB
########################################################################

def insert_articles(conn, feed_name, articles):
    cur = conn.cursor()

    for article in articles:
        title = article.get("title", "")
        link = article.get("link", "")
        description = article.get("description", "")
        pub_date = article.get("pub_date", "")
        guid = article.get("guid", "")
        categories = article.get("categories", "")
        content_encoded = article.get("content_encoded", "")

        # Skip if already exists
        cur.execute("""
            SELECT 1 FROM rss_articles WHERE link = ? OR guid = ? LIMIT 1
        """, (link, guid))
        if cur.fetchone():
            continue

        cur.execute("""
            INSERT INTO rss_articles (
                feed_name, title, link, pub_date, description,
                guid, categories, content_encoded
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            feed_name, title, link, pub_date, description,
            guid, categories, content_encoded
        ))

    conn.commit()

########################################################################
# RSS Feed URL and Parser
########################################################################

def build_feed_url(slug=""):
    return f"{BASE_URL}/category/{slug}/?outputType=xml" if slug else f"{BASE_URL}/?outputType=xml"

def fetch_feed_content(slug):
    url = build_feed_url(slug)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.content

def parse_feed(feed_content):
    feed = feedparser.parse(feed_content)
    articles = []

    try:
        root = ET.fromstring(feed_content)
        items = root.findall(".//item")
    except ET.ParseError:
        items = []

    for i, entry in enumerate(feed.entries):
        title = entry.get("title", "")
        link = entry.get("link", "")
        description = entry.get("description", "")

        # Normalize pub_date to ISO 8601 for SQLite
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime.datetime.fromtimestamp(mktime(entry.published_parsed))
            pub_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            raw = entry.get("published", "") or entry.get("pubDate", "")
            try:
                dt = datetime.datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %z")
                pub_date = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pub_date = None

        guid = entry.get("id", "") or entry.get("guid", "")
        categories = ", ".join([tag.term for tag in entry.tags]) if "tags" in entry else ""

        content_encoded = ""
        try:
            content_encoded = items[i].find(
                "{http://purl.org/rss/1.0/modules/content/}encoded"
            ).text or ""
        except Exception:
            pass

        articles.append({
            "title": title,
            "link": link,
            "description": description,
            "pub_date": pub_date,
            "guid": guid,
            "categories": categories,
            "content_encoded": content_encoded
        })

    return articles

########################################################################
# Main Pipeline
########################################################################

def run_pipeline(db_name="rss_data7.db"):
    start_time = time.time()
    conn = setup_database(db_name)

    for slug in SECTION_SLUGS:
        feed_name = slug if slug else "homepage"
        print(f"\n=== Processing feed: {feed_name} ===")

        try:
            content = fetch_feed_content(slug)
            articles = parse_feed(content)
            insert_articles(conn, feed_name, articles)
            print(f"✅ Inserted {len(articles)} articles from '{feed_name}'.")
        except Exception as e:
            print(f"❌ Error processing feed '{feed_name}': {e}")

    conn.close()
    print(f"\n✅ All feeds processed in {time.time() - start_time:.2f} seconds.")

########################################################################
# Entry Point
########################################################################

if __name__ == "__main__":
    run_pipeline()

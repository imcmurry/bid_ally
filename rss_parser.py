# rss_parser.py
import xml.etree.ElementTree as ET
import config
import sqlite3


def parse_rss_feed(rss_file_path: str) -> list[dict]:
    """
    Parses a local RSS XML file containing items like:

        <item>
          <title><![CDATA[ ... ]]></title>
          <link>...</link>
          <description><![CDATA[ ... ]]></description>
          <content:encoded><![CDATA[ <p>...</p> ]]></content:encoded>
          ...
        </item>

    Returns a list of articles, each a dict with:
      - "title": str
      - "link": str
      - "description": str
      - "content": str (the text/HTML under <content:encoded> if present)
    """
    articles = []
    try:
        tree = ET.parse(rss_file_path)
    except Exception as e:
        print(f"⚠️ Error parsing RSS file {rss_file_path}: {e}")
        return articles

    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        print(f"⚠️ RSS file {rss_file_path} does not contain a <channel> element.")
        return articles

    for item in channel.findall("item"):
        title = item.findtext("title", default="No Title").strip()
        link = item.findtext("link", default="No Link").strip()
        description = item.findtext("description", default="No Description").strip()
        
        # For the <content:encoded> node, we look up the config-defined namespace
        content_node = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        # if you prefer using config.XML_NAMESPACES, you can do:
        # content_node = item.find("content:encoded", config.XML_NAMESPACES)
        
        content_text = content_node.text.strip() if (content_node is not None and content_node.text) else ""

        articles.append({
            "title": title,
            "link": link,
            "description": description,
            "content": content_text
        })

    return articles


def load_articles_from_db(db_path=config.DB_NAME):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Select only articles from the past 1 month based on pub_date
    cursor.execute("""
        SELECT title, description, content_encoded, link 
        FROM rss_articles
        WHERE pub_date >= datetime('now', '-1 month')
    """)
    rows = cursor.fetchall()
    conn.close()

    articles = [
        {
            "title": row[0],
            "description": row[1],
            "content_encoded": row[2],
            "link": row[3]
        }
        for row in rows
    ]
    return articles


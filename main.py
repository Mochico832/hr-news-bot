import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# まずはここだけ触ればOK：監視したい会社名
COMPANIES = [
    "artience",
    "DIC",
    "Mimaki",
]

def google_news_rss_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"

def fetch_rss_titles(url: str, limit: int = 5):
    with urllib.request.urlopen(url, timeout=20) as r:
        xml_bytes = r.read()

    root = ET.fromstring(xml_bytes)

    # RSSの<title>を抜く（最初の<title>はフィード名なので除外）
    titles = [elem.text for elem in root.findall(".//item/title") if elem.text]
    return titles[:limit]

def main():
    print("=== HR News Bot: RSS test ===")

    for company in COMPANIES:
        url = google_news_rss_url(
    f'("{company}") (人事 OR 異動 OR 就任 OR 退任 OR 昇進 OR 役員 OR 社長 OR 任命 OR 発令 '
    f'OR appointment OR appointed OR resignation OR resigned OR promotion OR executive)')
        print(f"\n--- {company} ---")
        print(url)

        try:
            titles = fetch_rss_titles(url, limit=5)
            if not titles:
                print("No results.")
            else:
                for i, t in enumerate(titles, 1):
                    print(f"{i}. {t}")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    main()

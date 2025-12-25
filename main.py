import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# 監視したい会社名
COMPANIES = [
    "artience",
    "DIC",
    "Mimaki",
]

# 人事っぽいキーワード（タイトル＋概要の両方に当てる）
HR_KEYWORDS = [
    "人事", "異動", "就任", "退任", "昇進", "新任", "任命", "発令",
    "役員", "社長", "取締役", "執行役員", "CEO", "CFO", "COO",
    "appointment", "appointed", "resignation", "resigned", "promotion", "executive"
]

# ノイズになりがちな単語（多いなら増やす）
NOISE_KEYWORDS = [
    "決算", "業績", "売上", "株価", "新製品", "キャンペーン", "広告", "インタビュー",
]

def google_news_rss_url(company: str) -> str:
    # 会社名 + 人事ワード（広めに取って、後段でフィルタするのが安全）
    query = (
        f'("{company}") ('
        f'人事 OR 異動 OR 就任 OR 退任 OR 昇進 OR 役員 OR 社長 OR 任命 OR 発令 '
        f'OR appointment OR appointed OR resignation OR resigned OR promotion OR executive)'
    )
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"

def is_hr_text(text: str) -> bool:
    t = (text or "").lower()
    # 人事キーワードが1つでも含まれる
    has_hr = any(k.lower() in t for k in HR_KEYWORDS)
    # ノイズワードが多い場合は弾く（必要ならOFFでもOK）
    has_noise = any(k.lower() in t for k in NOISE_KEYWORDS)
    return has_hr and not has_noise

def parse_pubdate_to_jst_date(pubdate_text: str):
    # RSSのpubDateは "Tue, 26 Dec 2025 01:23:00 GMT" みたいな形式が多い
    if not pubdate_text:
        return None
    dt = parsedate_to_datetime(pubdate_text)
    if dt.tzinfo is None:
        # 念のためUTC扱い
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(JST).date()

def fetch_rss_items(url: str, limit: int = 30):
    with urllib.request.urlopen(url, timeout=20) as r:
        xml_bytes = r.read()

    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pubdate = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        items.append({
            "title": title,
            "link": link,
            "pubDate": pubdate,
            "description": desc,
        })
    return items

def main():
    today_jst = datetime.now(JST).date()
    print(f"=== HR News Bot: today only (JST) ===")
    print(f"Today(JST): {today_jst}")

    for company in COMPANIES:
        url = google_news_rss_url(company)
        print(f"\n--- {company} ---")
        print(url)

        try:
            items = fetch_rss_items(url, limit=50)

            # 今日(JST)だけ
            today_items = []
            for it in items:
                d = parse_pubdate_to_jst_date(it["pubDate"])
                if d == today_jst:
                    today_items.append(it)

            # さらに「人事っぽい」ものだけ（タイトル＋概要で判定）
            filtered = []
            for it in today_items:
                text = it["title"] + " " + it["description"]
                if is_hr_text(text):
                    filtered.append(it)

            if not filtered:
                print("No HR-like results for today (filtered).")
                continue

            for i, it in enumerate(filtered, 1):
                d = parse_pubdate_to_jst_date(it["pubDate"])
                print(f"{i}. [{d}] {it['title']}")
                print(f"   {it['link']}")

        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    main()

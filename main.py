import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

JST = ZoneInfo("Asia/Tokyo")

# 監視したい会社名
COMPANIES = [
    "artience",
    "DIC",
    "Mimaki",
]

# 人事っぽいキーワード（タイトル＋概要に当てる）
HR_KEYWORDS = [
    "人事", "異動", "就任", "退任", "昇進", "新任", "任命", "発令",
    "役員", "社長", "取締役", "執行役員", "CEO", "CFO", "COO",
    "appointment", "appointed", "resignation", "resigned",
    "promotion", "executive"
]

# ノイズになりがちな単語（多いなら増やす）
NOISE_KEYWORDS = [
    "決算", "業績", "売上", "株価", "新製品",
    "キャンペーン", "広告", "インタビュー",
]

# 前回までに見たURLを保存するファイル
SEEN_FILE = Path("seen_links.txt")
MAX_SEEN = 2000  # 記憶が増えすぎないよう上限

def load_seen_links() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    lines = SEEN_FILE.read_text(encoding="utf-8").splitlines()
    return set(line.strip() for line in lines if line.strip())

def save_seen_links(seen: set[str]):
    links = sorted(seen)
    if len(links) > MAX_SEEN:
        links = links[-MAX_SEEN:]
    SEEN_FILE.write_text("\n".join(links) + "\n", encoding="utf-8")

def google_news_rss_url(company: str) -> str:
    query = (
        f'("{company}") ('
        f'人事 OR 異動 OR 就任 OR 退任 OR 昇進 OR 役員 OR 社長 OR 任命 OR 発令 '
        f'OR appointment OR appointed OR resignation OR resigned '
        f'OR promotion OR executive)'
    )
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"

def is_hr_text(text: str) -> bool:
    t = (text or "").lower()
    has_hr = any(k.lower() in t for k in HR_KEYWORDS)
    has_noise = any(k.lower() in t for k in NOISE_KEYWORDS)
    return has_hr and not has_noise

def parse_pubdate_to_jst(pubdate_text: str):
    if not pubdate_text:
        return None
    dt = parsedate_to_datetime(pubdate_text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(JST)

def fetch_rss_items(url: str, limit: int = 50):
    with urllib.request.urlopen(url, timeout=20) as r:
        xml_bytes = r.read()

    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item")[:limit]:
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "pubDate": (item.findtext("pubDate") or "").strip(),
            "description": (item.findtext("description") or "").strip(),
        })
    return items

def main():
    now_jst = datetime.now(JST)
    since = now_jst - timedelta(hours=24)

    # 前回までに見たURLを読み込み
    seen = load_seen_links()

    print("=== HR News Bot: last 24 hours (dedupe by URL) ===")
    print(f"Now (JST): {now_jst}")
    print(f"Since (JST): {since}")
    print(f"Seen links loaded: {len(seen)}")

    # 今回新たに追加したURL（最後にまとめて保存）
    newly_seen = set()

    for company in COMPANIES:
        url = google_news_rss_url(company)
        print(f"\n--- {company} ---")
        print(url)

        try:
            items = fetch_rss_items(url, limit=50)
            recent_hr_items = []

            for it in items:
                pub_jst = parse_pubdate_to_jst(it["pubDate"])
                if not pub_jst:
                    continue
                if pub_jst < since:
                    continue

                text = it["title"] + " " + it["description"]
                if is_hr_text(text):
                    recent_hr_items.append((pub_jst, it))

            if not recent_hr_items:
                print("No HR-like results in last 24 hours.")
                continue

            # 新しい順
            recent_hr_items.sort(key=lambda x: x[0], reverse=True)

            # URLで「新規だけ」に絞る
            new_items = []
            for d, it in recent_hr_items:
                link = it.get("link", "")
                if link and (link not in seen) and (link not in newly_seen):
                    new_items.append((d, it))

            if not new_items:
                print("No NEW HR-like results in last 24 hours (deduped).")
                continue

            for i, (d, it) in enumerate(new_items, 1):
                print(f"{i}. [{d.strftime('%Y-%m-%d %H:%M')}] {it['title']}")
                print(f"   {it['link']}")
                newly_seen.add(it["link"])

        except Exception as e:
            print(f"ERROR: {e}")

    # 見たURLを保存（次回以降に除外される）
    if newly_seen:
        seen.update(newly_seen)
        save_seen_links(seen)

    print(f"\n[seen_links.txt] added this run = {len(newly_seen)}, total seen = {len(seen)}")

if __name__ == "__main__":
    main()

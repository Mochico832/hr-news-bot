import os
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

JST = ZoneInfo("Asia/Tokyo")

# ===== 監視対象（ここだけ将来いじればOK）=====
# display_name: メール表示用
# aliases: 表記ゆれ（日本語/英語/略称）
COMPANY_TARGETS = [
    {
        "display_name": "リコー株式会社",
        "aliases": ["リコー", "リコー株式会社", "RICOH", "Ricoh", "Ricoh Co., Ltd.", "Ricoh Company, Ltd."],
    },
    {
        "display_name": "株式会社SCREENグラフィックソリューションズ",
        "aliases": [
            "SCREENグラフィックソリューションズ",
            "株式会社SCREENグラフィックソリューションズ",
            "SCREEN Graphic Solutions",
            "SCREEN GP",
            "SCREEN",
            "SCREEN Holdings",
            "SCREENホールディングス",
            "SCREENホールディングス株式会社",
        ],
    },
    {
        "display_name": "株式会社ミヤコシ",
        "aliases": ["ミヤコシ", "株式会社ミヤコシ", "MIYAKOSHI", "Miyakoshi"],
    },
    {
        "display_name": "京セラ株式会社",
        "aliases": ["京セラ", "京セラ株式会社", "KYOCERA", "Kyocera", "Kyocera Corporation"],
    },
    {
        "display_name": "コニカミノルタ株式会社",
        "aliases": ["コニカミノルタ", "コニカ ミノルタ", "コニカミノルタ株式会社", "KONICA MINOLTA", "Konica Minolta"],
    },
    {
        "display_name": "富士フィルム株式会社",
        "aliases": ["富士フイルム", "富士フィルム", "富士フイルム株式会社", "FUJIFILM", "Fujifilm", "FUJIFILM Corporation"],
    },
    {
        "display_name": "セイコーエプソン株式会社",
        "aliases": ["セイコーエプソン", "セイコーエプソン株式会社", "エプソン", "EPSON", "Seiko Epson", "Seiko Epson Corporation"],
    },
    {
        "display_name": "武藤工業株式会社",
        "aliases": ["武藤工業", "武藤工業株式会社", "MUTOH", "Mutoh", "Mutoh Holdings", "MUTOH Holdings"],
    },
    {
        "display_name": "ブラザー工業株式会社",
        "aliases": ["ブラザー工業", "ブラザー工業株式会社", "ブラザー", "Brother", "BROTHER", "Brother Industries", "Brother Industries, Ltd."],
    },
]

# 人事っぽいキーワード（タイトル＋概要に当てる）
HR_KEYWORDS = [
    "人事", "異動", "就任", "退任", "昇進", "新任", "任命", "発令",
    "役員", "社長", "取締役", "執行役員", "代表取締役",
    "CEO", "CFO", "COO",
    "appointment", "appointed",
    "resignation", "resigned",
    "promotion", "executive", "board", "management",
]

# ノイズになりがちな単語（多いなら増やす）
NOISE_KEYWORDS = [
    "決算", "業績", "売上", "株価",
    "新製品", "キャンペーン", "広告", "インタビュー",
    "採用", "求人", "募集", "新卒", "キャリア採用", "インターン",
    "recruit", "hiring", "job", "intern",
]

# URL単位で重複除外するための保存ファイル
SEEN_FILE = Path("seen_links.txt")
MAX_SEEN = 5000

# 検索期間：直近24時間
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "24"))


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


def google_news_rss_url(query_terms: list[str]) -> str:
    """
    Google News RSS search URL.
    query_terms: ["リコー", "RICOH", ...] のような別名リスト
    """
    # 会社名はORで拾う（別名対応）
    company_query = " OR ".join([f'"{t}"' for t in query_terms if t])

    hr_query = (
        "(人事 OR 異動 OR 就任 OR 退任 OR 昇進 OR 新任 OR 任命 OR 発令 "
        "OR 役員 OR 社長 OR 取締役 OR 執行役員 OR 代表取締役 "
        "OR appointment OR appointed OR resignation OR resigned OR promotion OR executive OR board OR management)"
    )

    query = f"({company_query}) {hr_query}"
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
    req = urllib.request.Request(url, headers={"User-Agent": "hr-news-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
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


def send_mail_sendgrid(subject: str, body: str):
    # あなたの現行env名に合わせて維持（ここ重要）
    api_key = os.environ.get("SENDGRID_API_KEY")
    mail_from = os.environ.get("MAIL_FROM")
    mail_to = os.environ.get("MAIL_TO")

    print(
        "ENV CHECK:",
        "SENDGRID_API_KEY=", bool(api_key),
        "MAIL_FROM=", bool(mail_from),
        "MAIL_TO=", bool(mail_to),
        "LOOKBACK_HOURS=", LOOKBACK_HOURS
    )

    if not api_key or not mail_from or not mail_to:
        print("SendGrid secrets are missing. Skip sending email.")
        return

    payload = {
        "personalizations": [
            {"to": [{"email": addr.strip()} for addr in mail_to.split(",") if addr.strip()]}
        ],
        "from": {"email": mail_from, "name": "HR News Bot"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as res:
            print("Email sent:", res.status)  # 202なら成功
    except Exception as e:
        print("Email send failed:", e)


def main():
    now_jst = datetime.now(JST)
    since = now_jst - timedelta(hours=LOOKBACK_HOURS)

    seen = load_seen_links()

    print("=== HR News Bot ===")
    print(f"Lookback hours: {LOOKBACK_HOURS}")
    print(f"Now (JST):   {now_jst}")
    print(f"Since (JST): {since}")
    print(f"Seen links loaded: {len(seen)}")

    new_items_all = []
    new_links = set()

    for target in COMPANY_TARGETS:
        company_name = target["display_name"]
        aliases = target["aliases"]

        url = google_news_rss_url(aliases)
        print(f"\n--- {company_name} ---")
        print(url)

        try:
            items = fetch_rss_items(url, limit=50)

            filtered = []
            for it in items:
                pub_jst = parse_pubdate_to_jst(it["pubDate"])
                if not pub_jst:
                    continue
                if pub_jst < since:
                    continue

                text = it["title"] + " " + it["description"]
                if is_hr_text(text):
                    filtered.append((pub_jst, it))

            if not filtered:
                print("No HR-like results in lookback window.")
                continue

            filtered.sort(key=lambda x: x[0], reverse=True)

            new_items = []
            for d, it in filtered:
                link = it.get("link", "")
                if link and (link not in seen) and (link not in new_links):
                    new_items.append((d, it))

            if not new_items:
                print("No NEW HR-like results (deduped).")
                continue

            for i, (d, it) in enumerate(new_items, 1):
                print(f"{i}. [{d.strftime('%Y-%m-%d %H:%M')}] {it['title']}")
                print(f"   {it['link']}")

                new_items_all.append({
                    "company": company_name,
                    "datetime": d.strftime('%Y-%m-%d %H:%M'),
                    "title": it["title"],
                    "link": it["link"],
                })
                new_links.add(it["link"])

        except Exception as e:
            print("ERROR:", e)

    if new_links:
        seen.update(new_links)
        save_seen_links(seen)

    print(f"\n[seen_links.txt] added this run = {len(new_links)}, total seen = {len(seen)}")

    if new_items_all:
        new_items_all.sort(key=lambda x: (x["company"], x["datetime"]))

        lines = []
        lines.append("【人事ニュース｜新規（URL重複除外）】")
        lines.append(f"対象期間: {since.strftime('%Y-%m-%d %H:%M')} ～ {now_jst.strftime('%Y-%m-%d %H:%M')}（JST）")
        lines.append(f"新規: {len(new_items_all)}件")
        lines.append("")

        current_company = None
        for it in new_items_all:
            if it["company"] != current_company:
                current_company = it["company"]
                lines.append(f"\n=== {current_company} ===")
            lines.append(f'- [{it["datetime"]}] {it["title"]}')
            lines.append(f'  {it["link"]}')

        subject = f"【人事ニュース】直近{LOOKBACK_HOURS}h 新規{len(new_items_all)}件"
        body = "\n".join(lines)

        send_mail_sendgrid(subject, body)
    else:
        print("No new items. Email not sent.")


if __name__ == "__main__":
    main()

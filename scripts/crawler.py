
import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://wallstreetcn.com/live/global"
TZ = ZoneInfo("Asia/Taipei")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

RAW_OUTPUT = DATA_DIR / "raw_news.json"

DATE_RE = re.compile(r"^(\d{2})月(\d{2})日")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def normalize_text(s: str) -> str:
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("### ", "").replace("###", "")
    return s.strip()


def parse_date_line(line: str, now: datetime):
    m = DATE_RE.match(line.strip())
    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    year = now.year

    dt = datetime(year, month, day, tzinfo=TZ)

    # 處理跨年，避免 12月底 / 1月初抓錯年份
    if dt > now + timedelta(days=2):
        dt = datetime(year - 1, month, day, tzinfo=TZ)

    return dt.date()


def get_oldest_date_from_text(text: str, now: datetime):
    dates = []
    for line in text.splitlines():
        d = parse_date_line(line.strip(), now)
        if d:
            dates.append(d)

    if not dates:
        return None

    return min(dates)


def extract_news_items(text: str, now: datetime):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    items = []
    current_date = None
    current_item = None

    def flush_item():
        nonlocal current_item
        if not current_item:
            return

        raw_lines = current_item.get("lines", [])
        raw_lines = [
            normalize_text(x)
            for x in raw_lines
            if x.strip()
            and x.strip() not in ["展开", "只看重要的", "日期"]
            and not x.strip().startswith("[[[image_")
        ]

        if not raw_lines:
            current_item = None
            return

        headline = raw_lines[0]
        content = "\n".join(raw_lines[1:]).strip()

        # 如果 headline 太長，取前一段當標題
        if len(headline) > 120:
            content = headline
            headline = headline[:80] + "..."

        item = {
            "datetime": current_item["datetime"],
            "headline": headline,
            "content": content,
            "source": "華爾街見聞",
            "url": URL,
        }

        items.append(item)
        current_item = None

    for line in lines:
        line = line.strip()

        d = parse_date_line(line, now)
        if d:
            flush_item()
            current_date = d
            continue

        tm = TIME_RE.match(line)
        if tm and current_date:
            flush_item()

            hour = int(tm.group(1))
            minute = int(tm.group(2))

            dt = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hour,
                minute,
                tzinfo=TZ,
            )

            current_item = {
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "lines": [],
            }
            continue

        if current_item:
            current_item["lines"].append(line)

    flush_item()

    # 去重
    seen = set()
    unique = []
    for item in items:
        key = (item["datetime"], item["headline"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    unique.sort(key=lambda x: x["datetime"], reverse=True)
    return unique


def main():
    now = datetime.now(TZ)
    cutoff = now - timedelta(days=7)

    print(f"Now: {now}")
    print(f"Cutoff: {cutoff}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = browser.new_page(
            viewport={"width": 1440, "height": 1800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )

        page.goto(URL, wait_until="networkidle", timeout=90000)
        time.sleep(5)

        last_height = 0
        same_height_count = 0

        for i in range(100):
            text = page.locator("body").inner_text(timeout=30000)
            oldest = get_oldest_date_from_text(text, now)

            print(f"Scroll {i + 1}, oldest date: {oldest}")

            if oldest and oldest <= cutoff.date():
                print("Reached one week ago.")
                break

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)

            height = page.evaluate("document.body.scrollHeight")
            if height == last_height:
                same_height_count += 1
            else:
                same_height_count = 0

            last_height = height

            if same_height_count >= 5:
                print("Page height no longer changes. Stop scrolling.")
                break

        final_text = page.locator("body").inner_text(timeout=30000)
        browser.close()

    all_items = extract_news_items(final_text, now)

    filtered_items = []
    for item in all_items:
        dt = datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        if cutoff <= dt <= now:
            filtered_items.append(item)

    result = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "source": URL,
        "timezone": "Asia/Taipei",
        "count": len(filtered_items),
        "items": filtered_items,
    }

    RAW_OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved {len(filtered_items)} raw news items to {RAW_OUTPUT}")


if __name__ == "__main__":
    main()

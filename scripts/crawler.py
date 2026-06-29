import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://wallstreetcn.com/live/global"

UTC_TZ = ZoneInfo("UTC")
TW_TZ = ZoneInfo("Asia/Taipei")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

RAW_OUTPUT = DATA_DIR / "raw_news.json"

DATE_RE = re.compile(r"^(\d{2})月(\d{2})日")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def log(msg):
    print(msg, flush=True)


def normalize_text(s):
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("### ", "").replace("###", "")
    return s.strip()


def get_fetch_start_time_tw(now_tw):
    """
    規則全部以台灣時間計算：
    - 如果今天是禮拜一：抓上週五 17:00 台灣時間之後
    - 其他日期：抓前一天 17:00 台灣時間之後
    """

    if now_tw.weekday() == 0:
        start_date = now_tw.date() - timedelta(days=3)
    else:
        start_date = now_tw.date() - timedelta(days=1)

    return datetime(
        start_date.year,
        start_date.month,
        start_date.day,
        17,
        0,
        tzinfo=TW_TZ,
    )


def parse_date_line_as_utc_date(line, now_tw):
    """
    華爾街見聞頁面只有 06月29日 這種格式，沒有年份。
    這裡先用台灣時間的年份補上，但後面會把解析出的日期時間視為 UTC，再轉台灣時間。
    """

    m = DATE_RE.match(line.strip())

    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    year = now_tw.year

    dt = datetime(year, month, day, tzinfo=UTC_TZ)

    # 處理跨年，例如 1月初看到 12月31日
    if dt.astimezone(TW_TZ) > now_tw + timedelta(days=2):
        dt = datetime(year - 1, month, day, tzinfo=UTC_TZ)

    return dt.date()


def convert_page_time_utc_to_tw(date_obj, hour, minute):
    """
    網頁上解析到的日期與時間，視為 UTC。
    寫入 data 時轉成台灣時間。
    """

    dt_utc = datetime(
        date_obj.year,
        date_obj.month,
        date_obj.day,
        hour,
        minute,
        tzinfo=UTC_TZ,
    )

    dt_tw = dt_utc.astimezone(TW_TZ)

    return dt_tw


def extract_news_items(text, now_tw):
    """
    從頁面文字抽取新聞。
    這版邏輯：
    - 頁面日期時間先視為 UTC
    - 轉成台灣時間後再寫入 datetime
    """

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    items = []
    current_utc_date = None
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

        if len(headline) > 120:
            content = headline
            headline = headline[:80] + "..."

        item = {
            "datetime": current_item["datetime_tw"],
            "datetime_source_utc": current_item["datetime_utc"],
            "headline": headline,
            "content": content,
            "source": "華爾街見聞",
            "url": URL,
            "timezone": "Asia/Taipei",
        }

        items.append(item)
        current_item = None

    for line in lines:
        d = parse_date_line_as_utc_date(line, now_tw)

        if d:
            flush_item()
            current_utc_date = d
            continue

        tm = TIME_RE.match(line)

        if tm and current_utc_date:
            flush_item()

            hour = int(tm.group(1))
            minute = int(tm.group(2))

            dt_tw = convert_page_time_utc_to_tw(current_utc_date, hour, minute)

            dt_utc = datetime(
                current_utc_date.year,
                current_utc_date.month,
                current_utc_date.day,
                hour,
                minute,
                tzinfo=UTC_TZ,
            )

            current_item = {
                "datetime_tw": dt_tw.strftime("%Y-%m-%d %H:%M"),
                "datetime_utc": dt_utc.strftime("%Y-%m-%d %H:%M"),
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


def get_oldest_datetime_tw(items):
    if not items:
        return None

    dts = []

    for item in items:
        try:
            dt = datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M").replace(tzinfo=TW_TZ)
            dts.append(dt)
        except Exception:
            pass

    if not dts:
        return None

    return min(dts)


def main():
    now_tw = datetime.now(TW_TZ)
    start_time_tw = get_fetch_start_time_tw(now_tw)

    log("========== Crawl Start ==========")
    log(f"Now Taiwan Time: {now_tw.strftime('%Y-%m-%d %H:%M')}")
    log(f"Fetch Start Time Taiwan: {start_time_tw.strftime('%Y-%m-%d %H:%M')}")
    log("Rule timezone: Asia/Taipei")
    log("Important: Page parsed times are treated as UTC, then converted to Asia/Taipei.")

    if now_tw.weekday() == 0:
        log("Rule: Today is Monday in Taiwan, fetching news after last Friday 17:00 Taiwan time.")
    else:
        log("Rule: Today is not Monday in Taiwan, fetching news after previous day 17:00 Taiwan time.")

    with sync_playwright() as p:
        log("Launching Chromium...")

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1440, "height": 1800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="zh-TW",
            timezone_id="Asia/Taipei",
        )

        page = context.new_page()

        log(f"Opening URL: {URL}")

        page.goto(URL, wait_until="networkidle", timeout=90000)
        time.sleep(5)

        last_height = 0
        same_height_count = 0
        latest_items_count = 0

        for i in range(80):
            text = page.locator("body").inner_text(timeout=30000)
            items = extract_news_items(text, now_tw)
            oldest_dt_tw = get_oldest_datetime_tw(items)

            latest_items_count = len(items)

            log(
                f"Scroll {i + 1}: "
                f"items={len(items)}, "
                f"oldest_tw={oldest_dt_tw.strftime('%Y-%m-%d %H:%M') if oldest_dt_tw else 'N/A'}"
            )

            if oldest_dt_tw and oldest_dt_tw <= start_time_tw:
                log("Reached required Taiwan start time. Stop scrolling.")
                break

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)

            height = page.evaluate("document.body.scrollHeight")

            if height == last_height:
                same_height_count += 1
                log(f"Page height unchanged. Count={same_height_count}")
            else:

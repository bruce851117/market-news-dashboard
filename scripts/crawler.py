import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from playwright.sync_api import sync_playwright

CRAWLER_VERSION = "tw-time-force-v4"

URL = "https" + "://wallstreetcn.com/live/global"

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
    s = str(s or "")
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("### ", "").replace("###", "")
    return s.strip()


def get_fetch_start_time_tw(now_tw):
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
        tzinfo=TW_TZ
    )


def parse_page_date_as_utc(line, now_tw):
    m = DATE_RE.match(line.strip())

    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    year = now_tw.year

    dt_utc = datetime(year, month, day, 0, 0, tzinfo=UTC_TZ)

    if dt_utc.astimezone(TW_TZ) > now_tw + timedelta(days=2):
        dt_utc = datetime(year - 1, month, day, 0, 0, tzinfo=UTC_TZ)

    return dt_utc.date()


def make_datetime_utc_and_tw(date_obj, hour, minute):
    dt_utc = datetime(
        date_obj.year,
        date_obj.month,
        date_obj.day,
        hour,
        minute,
        tzinfo=UTC_TZ
    )

    dt_tw = dt_utc.astimezone(TW_TZ)

    return dt_utc, dt_tw


def extract_news_items(text, now_tw):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    items = []
    current_utc_date = None
    current_item = None

    def flush_item():
        nonlocal current_item

        if current_item is None:
            return

        raw_lines = current_item.get("lines", [])

        cleaned_lines = []

        for x in raw_lines:
            x = x.strip()

            if not x:
                continue

            if x in ["展开", "只看重要的", "日期"]:
                continue

            if x.startswith("[[[image_"):
                continue

            cleaned_lines.append(normalize_text(x))

        if len(cleaned_lines) == 0:
            current_item = None
            return

        headline = cleaned_lines[0]
        content = "\n".join(cleaned_lines[1:]).strip()

        if len(headline) > 120:
            content = headline
            headline = headline[:80] + "..."

        item = dict()
        item["datetime"] = current_item["datetime_tw"]
        item["datetime_source_utc"] = current_item["datetime_utc"]
        item["headline"] = headline
        item["content"] = content
        item["source"] = "華爾街見聞"
        item["url"] = URL
        item["timezone"] = "Asia/Taipei"

        items.append(item)

        current_item = None

    for line in lines:
        parsed_date = parse_page_date_as_utc(line, now_tw)

        if parsed_date is not None:
            flush_item()
            current_utc_date = parsed_date
            continue

        time_match = TIME_RE.match(line)

        if time_match and current_utc_date is not None:
            flush_item()

            hour = int(time_match.group(1))
            minute = int(time_match.group(2))

            dt_utc, dt_tw = make_datetime_utc_and_tw(
                current_utc_date,
                hour,
                minute
            )

            current_item = dict()
            current_item["datetime_utc"] = dt_utc.strftime("%Y-%m-%d %H:%M")
            current_item["datetime_tw"] = dt_tw.strftime("%Y-%m-%d %H:%M")
            current_item["lines"] = []

            continue

        if current_item is not None:
            current_item["lines"].append(line)

    flush_item()

    seen = set()
    unique = []

    for item in items:
        key = (item.get("datetime"), item.get("headline"))

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    unique.sort(key=lambda x: x["datetime"], reverse=True)

    return unique


def get_oldest_datetime_tw(items):
    dts = []

    for item in items:
        try:
            dt = datetime.strptime(
                item["datetime"],
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=TW_TZ)

            dts.append(dt)

        except Exception:
            continue

    if len(dts) == 0:
        return None

    return min(dts)


def main():
    log("========== Crawl Start ==========")
    log("CRAWLER_VERSION: " + CRAWLER_VERSION)
    log("URL: " + URL)

    now_tw = datetime.now(TW_TZ)
    start_time_tw = get_fetch_start_time_tw(now_tw)

    log("Now Taiwan Time: " + now_tw.strftime("%Y-%m-%d %H:%M"))
    log("Fetch Start Time Taiwan: " + start_time_tw.strftime("%Y-%m-%d %H:%M"))
    log("Page time assumption: page datetime is UTC, then converted to Asia/Taipei.")

    if now_tw.weekday() == 0:
        log("Rule: Monday Taiwan time, fetch after last Friday 17:00 Taiwan time.")
    else:
        log("Rule: Non-Monday Taiwan time, fetch after previous day 17:00 Taiwan time.")

    with sync_playwright() as p:
        log("Launching Chromium...")

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = browser.new_context(
            viewport=dict(
                width=1440,
                height=1800
            ),
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="zh-TW",
            timezone_id="Asia/Taipei"
        )

        page = context.new_page()

        log("Opening URL: " + URL)

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

            if oldest_dt_tw:
                oldest_log = oldest_dt_tw.strftime("%Y-%m-%d %H:%M")
            else:
                oldest_log = "N/A"

            log(
                "Scroll "
                + str(i + 1)
                + ": items="
                + str(len(items))
                + ", oldest_tw="
                + oldest_log
            )

            if oldest_dt_tw and oldest_dt_tw <= start_time_tw:
                log("Reached required Taiwan start time. Stop scrolling.")
                break

            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)

            height = page.evaluate("document.body.scrollHeight")

            if height == last_height:
                same_height_count += 1
                log("Page height unchanged. Count=" + str(same_height_count))
            else:
                same_height_count = 0

            last_height = height

            if same_height_count >= 5:
                log("Page height no longer changes. Stop scrolling.")
                break

        log("Finished scrolling. Last detected items count: " + str(latest_items_count))

        final_text = page.locator("body").inner_text(timeout=30000)

        context.close()
        browser.close()

    all_items = extract_news_items(final_text, now_tw)

    filtered_items = []

    for item in all_items:
        try:
            dt_tw = datetime.strptime(
                item["datetime"],
                "%Y-%m-%d %H:%M"
            ).replace(tzinfo=TW_TZ)

        except Exception:
            continue

        if start_time_tw <= dt_tw <= now_tw:
            filtered_items.append(item)

    filtered_items.sort(key=lambda x: x["datetime"], reverse=True)

    result = dict()
    result["generated_at"] = now_tw.strftime("%Y-%m-%d %H:%M")
    result["fetch_start_time"] = start_time_tw.strftime("%Y-%m-%d %H:%M")
    result["fetch_end_time"] = now_tw.strftime("%Y-%m-%d %H:%M")
    result["source"] = URL
    result["timezone"] = "Asia/Taipei"
    result["source_time_assumption"] = "page datetime parsed as UTC and converted to Asia/Taipei"
    result["crawler_version"] = CRAWLER_VERSION
    result["count"] = len(filtered_items)
    result["items"] = filtered_items

    RAW_OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    log("========== Crawl Finished ==========")
    log("Raw items before time filter: " + str(len(all_items)))
    log("Raw items after Taiwan time filter: " + str(len(filtered_items)))
    log("Saved raw news to: " + str(RAW_OUTPUT))
    log("Output timezone: Asia/Taipei")
    log("Output generated_at: " + result["generated_at"])
    log("Output fetch_start_time: " + result["fetch_start_time"])
    log("Output fetch_end_time: " + result["fetch_end_time"])

    if filtered_items:
        log("Latest item in Taiwan time:")
        log(json.dumps(filtered_items[0], ensure_ascii=False, indent=2))

        log("Oldest item in Taiwan time:")
        log(json.dumps(filtered_items[-1], ensure_ascii=False, indent=2))
    else:
        log("Warning: No items captured after Taiwan time filter.")


if __name__ == "__main__":
    main()

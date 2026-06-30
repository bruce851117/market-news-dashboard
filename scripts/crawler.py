import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from playwright.sync_api import sync_playwright


CRAWLER_VERSION = "tw-browser-time-v9-feed-scope-date-marker"
URL = "https" + "://wallstreetcn.com/live/global"
TW_TZ = ZoneInfo("Asia/Taipei")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
RAW_OUTPUT = DATA_DIR / "raw_news.json"

DEBUG_DIR = DATA_DIR / "debug"
DEBUG_DIR.mkdir(exist_ok=True)
SAVE_DEBUG = True

DATE_LINE_RE = re.compile(
    r"^(\d{1,2})月(\d{1,2})日(?:[，,\s、]*星期[一二三四五六日天])?(?:[，,\s、]*\d{2}:\d{2}:\d{2})?$"
)
DATE_MARKER_RE = re.compile(
    r"(\d{1,2}月\d{1,2}日(?:[，,\s、]*星期[一二三四五六日天])?)"
)
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def log(msg):
    print(msg, flush=True)


def normalize_text(s):
    s = str(s or "")
    s = s.replace("\u3000", " ")
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("### ", "").replace("###", "")
    return s.strip()


def get_fetch_start_time_tw(now_tw):
    today_1700 = now_tw.replace(hour=17, minute=0, second=0, microsecond=0)

    if now_tw.weekday() == 0:
        fetch_start = today_1700 - timedelta(days=3)
        rule = "Monday Taiwan time, fetch after previous Friday 17:00 Taiwan time."
    else:
        fetch_start = today_1700 - timedelta(days=1)
        rule = "Non-Monday Taiwan time, fetch after previous day 17:00 Taiwan time."

    return fetch_start, rule


def parse_page_date_as_tw(line, now_tw):
    line = normalize_text(line)
    m = DATE_LINE_RE.match(line)

    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    year = now_tw.year

    dt = datetime(year, month, day, tzinfo=TW_TZ)

    if dt > now_tw + timedelta(days=7):
        dt = datetime(year - 1, month, day, tzinfo=TW_TZ)

    return dt.date()


def split_inline_date_markers(lines):
    output = []

    for raw_line in lines:
        line = normalize_text(raw_line)

        if not line:
            continue

        matches = list(DATE_MARKER_RE.finditer(line))

        if not matches:
            output.append(line)
            continue

        pos = 0

        for m in matches:
            before = normalize_text(line[pos:m.start()])
            marker = normalize_text(m.group(1))

            if before:
                output.append(before)

            if marker:
                output.append(marker)

            pos = m.end()

        after = normalize_text(line[pos:])

        if after:
            output.append(after)

    return output


def extract_feed_lines(page_text):
    raw_lines = [normalize_text(x) for x in page_text.splitlines() if normalize_text(x)]

    # 只解析「日期」之後的快訊列表，避免 header/nav 污染
    start_idx = 0
    for idx, line in enumerate(raw_lines):
        if line == "日期":
            start_idx = idx + 1
            break

    # 只解析到「实时行情」之前，避免行情、財經日曆、footer 污染
    end_idx = len(raw_lines)
    stop_markers = [
        "实时行情",
        "即時行情",
        "财经日历",
        "財經日曆",
        "华尔街见闻",
        "華爾街見聞",
        "关于我们",
        "關於我們",
    ]

    for idx in range(start_idx, len(raw_lines)):
        if raw_lines[idx] in stop_markers:
            end_idx = idx
            break

    feed_lines = raw_lines[start_idx:end_idx]
    feed_lines = split_inline_date_markers(feed_lines)

    return feed_lines


def is_date_line(line, now_tw):
    return parse_page_date_as_tw(line, now_tw) is not None


def is_time_line(line):
    return TIME_RE.match(normalize_text(line)) is not None


def make_datetime_tw(date_obj, hour, minute):
    return datetime(
        date_obj.year,
        date_obj.month,
        date_obj.day,
        hour,
        minute,
        tzinfo=TW_TZ,
    )


def should_skip_line(line):
    line = normalize_text(line)

    skip_exact = {
        "展开",
        "收起",
        "数据解读",
        "相关文章：",
        "实时行情",
        "即時行情",
        "财经日历",
        "財經日曆",
        "查看更多 >",
        "查看更多",
    }

    if line in skip_exact:
        return True

    return False


def is_junk_item(item):
    headline = normalize_text(item.get("headline", ""))
    content = normalize_text(item.get("content", ""))

    if not headline:
        return True

    text = headline + "\n" + content

    widget_keywords = [
        "实时行情",
        "即時行情",
        "财经日历",
        "財經日曆",
        "查看更多",
        "综览",
        "綜覽",
        "外汇",
        "外匯",
        "债券",
        "債券",
        "资产",
        "資產",
        "现价",
        "現價",
        "涨跌",
        "漲跌",
        "DXY.OTC",
        "EURUSD.OTC",
        "USDJPY.OTC",
        "XAUUSD.OTC",
    ]

    if sum(1 for k in widget_keywords if k in text) >= 3:
        return True

    meaningful = re.sub(r"[^\w\u4e00-\u9fff]", "", headline)

    if len(meaningful) < 2:
        return True

    return False


def extract_news_items(page_text, now_tw):
    lines = extract_feed_lines(page_text)

    items = []
    current_date = now_tw.date()

    i = 0

    while i < len(lines):
        line = normalize_text(lines[i])

        parsed_date = parse_page_date_as_tw(line, now_tw)

        if parsed_date:
            current_date = parsed_date
            i += 1
            continue

        tm = TIME_RE.match(line)

        if not tm:
            i += 1
            continue

        hour = int(tm.group(1))
        minute = int(tm.group(2))

        dt_tw = make_datetime_tw(current_date, hour, minute)

        if i + 1 >= len(lines):
            i += 1
            continue

        headline = normalize_text(lines[i + 1])

        if is_time_line(headline) or is_date_line(headline, now_tw) or should_skip_line(headline):
            i += 1
            continue

        content_lines = []
        j = i + 2

        while j < len(lines):
            next_line = normalize_text(lines[j])

            if is_time_line(next_line) or is_date_line(next_line, now_tw):
                break

            if should_skip_line(next_line):
                j += 1
                continue

            content_lines.append(next_line)
            j += 1

        content = normalize_text("\n".join(content_lines))

        item = {
            "datetime": dt_tw.strftime("%Y-%m-%d %H:%M"),
            "headline": headline,
            "content": content,
            "source": "華爾街見聞",
            "url": URL,
            "timezone": "Asia/Taipei",
        }

        items.append(item)

        i = j

    return items


def parse_item_datetime_tw(item):
    try:
        return datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M").replace(tzinfo=TW_TZ)
    except Exception:
        return None


def get_oldest_datetime_tw(items):
    dts = [parse_item_datetime_tw(x) for x in items]
    dts = [x for x in dts if x]

    return min(dts) if dts else None


def get_latest_datetime_tw(items):
    dts = [parse_item_datetime_tw(x) for x in items]
    dts = [x for x in dts if x]

    return max(dts) if dts else None


def dedupe_items(items):
    seen = set()
    output = []

    for item in items:
        key = (
            item.get("datetime", ""),
            item.get("headline", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(item)

    output.sort(key=lambda x: x.get("datetime", ""), reverse=True)

    return output


def filter_items_in_range(items, fetch_start_tw, now_tw):
    output = []
    max_allowed = now_tw + timedelta(minutes=5)

    for item in items:
        dt = parse_item_datetime_tw(item)

        if not dt:
            continue

        if dt < fetch_start_tw:
            continue

        if dt > max_allowed:
            log(
                "Drop future item: "
                + item.get("datetime", "")
                + " headline="
                + item.get("headline", "")
            )
            continue

        output.append(item)

    output.sort(key=lambda x: x.get("datetime", ""), reverse=True)

    return output


def save_debug(scroll_no, page_text, feed_lines, parsed_items, clean_items):
    if not SAVE_DEBUG:
        return

    prefix = DEBUG_DIR / f"scroll_{scroll_no:02d}"

    prefix.with_suffix(".body_inner_text.txt").write_text(
        page_text,
        encoding="utf-8",
    )

    prefix.with_suffix(".feed_lines.txt").write_text(
        "\n".join(feed_lines),
        encoding="utf-8",
    )

    (DEBUG_DIR / f"scroll_{scroll_no:02d}.parsed_items.json").write_text(
        json.dumps(parsed_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (DEBUG_DIR / f"scroll_{scroll_no:02d}.clean_items.json").write_text(
        json.dumps(clean_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    log("========== Crawl Start ==========")
    log("CRAWLER_VERSION: " + CRAWLER_VERSION)
    log("URL: " + URL)

    now_tw = datetime.now(TW_TZ)
    fetch_start_tw, rule = get_fetch_start_time_tw(now_tw)

    log("Now Taiwan Time: " + now_tw.strftime("%Y-%m-%d %H:%M"))
    log("Fetch Start Time Taiwan: " + fetch_start_tw.strftime("%Y-%m-%d %H:%M"))
    log("Browser timezone: Asia/Taipei")
    log("Page time assumption: page datetime is already rendered in Asia/Taipei.")
    log("Rule: " + rule)

    all_items = []

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
            timezone_id="Asia/Taipei",
            locale="zh-TW",
            viewport={
                "width": 1440,
                "height": 1800,
            },
        )

        page = context.new_page()

        log("Opening URL: " + URL)

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(6000)

        max_scrolls = 45
        previous_count = 0
        no_growth_count = 0

        for scroll_no in range(1, max_scrolls + 1):
            page_text = page.locator("body").inner_text(timeout=60000)

            feed_lines = extract_feed_lines(page_text)

            parsed_items = dedupe_items(extract_news_items(page_text, now_tw))
            clean_items = dedupe_items([item for item in parsed_items if not is_junk_item(item)])

            all_items = dedupe_items(all_items + clean_items)

            save_debug(scroll_no, page_text, feed_lines, parsed_items, clean_items)

            oldest_tw = get_oldest_datetime_tw(all_items)
            latest_tw = get_latest_datetime_tw(all_items)


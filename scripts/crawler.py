import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from playwright.sync_api import sync_playwright


CRAWLER_VERSION = "tw-browser-time-v6-clean-stop"

URL = "https" + "://wallstreetcn.com/live/global"

TW_TZ = ZoneInfo("Asia/Taipei")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

RAW_OUTPUT = DATA_DIR / "raw_news.json"

DATE_RE = re.compile(r"^(\d{2})月(\d{2})日$")
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
    """
    全部用台灣時間計算：
    - 如果今天是禮拜一：抓上週五 17:00 台灣時間之後
    - 其他日期：抓前一天 17:00 台灣時間之後
    """
    today_1700 = now_tw.replace(hour=17, minute=0, second=0, microsecond=0)

    if now_tw.weekday() == 0:
        # Monday: previous Friday 17:00
        days_back = 3
        rule = "Monday Taiwan time, fetch after previous Friday 17:00 Taiwan time."
    else:
        # Other days: previous day 17:00
        days_back = 1
        rule = "Non-Monday Taiwan time, fetch after previous day 17:00 Taiwan time."

    fetch_start = today_1700 - timedelta(days=days_back)

    return fetch_start, rule


def parse_page_date_as_tw(line, now_tw):
    """
    華爾街見聞頁面常見日期格式：06月30日
    頁面瀏覽器 timezone 已設為 Asia/Taipei，所以直接視為台灣時間。
    """
    m = DATE_RE.match(line)
    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))

    year = now_tw.year
    dt = datetime(year, month, day, tzinfo=TW_TZ)

    # 年底跨年防呆：
    # 如果頁面日期比現在還晚超過 7 天，視為前一年。
    if dt > now_tw + timedelta(days=7):
        dt = datetime(year - 1, month, day, tzinfo=TW_TZ)

    return dt.date()


def make_datetime_tw(date_obj, hour, minute):
    return datetime(
        date_obj.year,
        date_obj.month,
        date_obj.day,
        hour,
        minute,
        tzinfo=TW_TZ,
    )


def is_date_line(line):
    return DATE_RE.match(line) is not None


def is_time_line(line):
    return TIME_RE.match(line) is not None


def is_obvious_page_widget_text(text):
    """
    過濾華爾街見聞頁面中的行情、財經日曆、側邊欄、導航區塊。
    這些區塊會污染 crawler 的停止判斷。
    """
    text = str(text or "")

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
        "商品",
        "债券",
        "債券",
        "资产",
        "資產",
        "现价",
        "現價",
        "涨跌",
        "漲跌",
        "美元指数",
        "美元指數",
        "DXY.OTC",
        "EURUSD.OTC",
        "USDJPY.OTC",
        "XAUUSD.OTC",
        "WTI原油",
        "财经日历",
        "2026-",
    ]

    hit_count = sum(1 for k in widget_keywords if k in text)

    # 命中多個 widget 關鍵字，幾乎一定不是單則新聞正文
    if hit_count >= 3:
        return True

    return False


def is_junk_item(item):
    headline = normalize_text(item.get("headline", ""))
    content = normalize_text(item.get("content", ""))
    text = headline + "\n" + content

    if not headline:
        return True

    hard_junk_headlines = [
        "实时行情",
        "即時行情",
        "财经日历",
        "財經日曆",
        "查看更多",
        "综览",
        "綜覽",
        "外汇",
        "外匯",
        "商品",
        "债券",
        "債券",
        "资产",
        "資產",
        "现价",
        "現價",
        "涨跌",
        "漲跌",
    ]

    if headline in hard_junk_headlines:
        return True

    if is_obvious_page_widget_text(text):
        return True

    # 跳過空 headline 或只有符號的內容
    if len(re.sub(r"[^\w\u4e00-\u9fff]", "", headline)) < 2:
        return True

    return False


def extract_news_items(text, now_tw):
    """
    從整頁 inner_text 解析快訊。

    基本結構通常是：
    06月30日
    08:09
    【新聞標題】
    新聞內容...
    08:01
    下一則...
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

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

        # 下一行通常是 headline
        if i + 1 >= len(lines):
            i += 1
            continue

        headline = normalize_text(lines[i + 1])

        # headline 不應該是日期或時間
        if is_date_line(headline) or is_time_line(headline):
            i += 1
            continue

        content_lines = []
        j = i + 2

        while j < len(lines):
            next_line = normalize_text(lines[j])

            # 遇到下一個日期或時間，代表下一則開始
            if is_date_line(next_line) or is_time_line(next_line):
                break

            # 一些頁面導航 / widget 起點，直接不要再吃進 content
            if next_line in [
                "实时行情",
                "即時行情",
                "财经日历",
                "財經日曆",
                "查看更多",
                "综览",
                "綜覽",
            ]:
                break

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
    dts = []

    for item in items:
        dt = parse_item_datetime_tw(item)
        if dt:
            dts.append(dt)

    if not dts:
        return None

    return min(dts)


def get_latest_datetime_tw(items):
    dts = []

    for item in items:
        dt = parse_item_datetime_tw(item)
        if dt:
            dts.append(dt)

    if not dts:
        return None

    return max(dts)


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


def filter_items_after_start(items, fetch_start_tw):
    output = []

    for item in items:
        dt = parse_item_datetime_tw(item)
        if not dt:
            continue

        if dt >= fetch_start_tw:
            output.append(item)

    output.sort(key=lambda x: x.get("datetime", ""), reverse=True)

    return output


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
    reached_start_count = 0

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

        max_scrolls = 40
        no_growth_count = 0
        previous_clean_count = 0

        for scroll_no in range(1, max_scrolls + 1):
            page_text = page.locator("body").inner_text(timeout=60000)

            parsed_items = extract_news_items(page_text, now_tw)
            parsed_items = dedupe_items(parsed_items)

            clean_items = [item for item in parsed_items if not is_junk_item(item)]
            clean_items = dedupe_items(clean_items)

            all_items = dedupe_items(all_items + clean_items)

            clean_oldest_tw = get_oldest_datetime_tw(clean_items)
            all_oldest_tw = get_oldest_datetime_tw(all_items)

            if clean_oldest_tw:
                clean_oldest_str = clean_oldest_tw.strftime("%Y-%m-%d %H:%M")
            else:
                clean_oldest_str = "None"

            if all_oldest_tw:
                all_oldest_str = all_oldest_tw.strftime("%Y-%m-%d %H:%M")
            else:
                all_oldest_str = "None"

            log(
                f"Scroll {scroll_no}: "
                f"parsed={len(parsed_items)}, "
                f"clean={len(clean_items)}, "
                f"all_clean={len(all_items)}, "
                f"clean_oldest_tw={clean_oldest_str}, "
                f"all_oldest_tw={all_oldest_str}"
            )

            if len(all_items) <= previous_clean_count:
                no_growth_count += 1
            else:
                no_growth_count = 0

            previous_clean_count = len(all_items)

            # 只有 clean oldest 達到抓取起點，才累計停止條件
            if all_oldest_tw and all_oldest_tw <= fetch_start_tw:
                reached_start_count += 1
                log(
                    "Reached start candidate "
                    + str(reached_start_count)
                    + "/5, all_oldest_tw="
                    + all_oldest_tw.strftime("%Y-%m-%d %H:%M")
                )

                # 連續 5 次都達標才停止，避免被頁面 widget 假時間誤導
                if reached_start_count >= 5:
                    log("Reached required Taiwan start time for 5 consecutive checks. Stop scrolling.")
                    break
            else:
                reached_start_count = 0

            # 如果已經很久沒有新增 clean item，且至少捲過一定次數，也停止
            if scroll_no >= 12 and no_growth_count >= 5:
                log("No new clean items for 5 consecutive scrolls. Stop scrolling.")
                break

            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(2500)

        browser.close()

    log("Finished scrolling. Last detected clean items count: " + str(len(all_items)))

    clean_all_items = [item for item in all_items if not is_junk_item(item)]
    clean_all_items = dedupe_items(clean_all_items)

    filtered_items = filter_items_after_start(clean_all_items, fetch_start_tw)

    latest_tw = get_latest_datetime_tw(filtered_items)
    oldest_tw = get_oldest_datetime_tw(filtered_items)

    output = {
        "generated_at": now_tw.strftime("%Y-%m-%d %H:%M"),
        "fetch_start_time": fetch_start_tw.strftime("%Y-%m-%d %H:%M"),
        "fetch_end_time": now_tw.strftime("%Y-%m-%d %H:%M"),
        "source": URL,
        "timezone": "Asia/Taipei",
        "source_time_assumption": "browser timezone Asia/Taipei; page datetime treated as Taiwan time",
        "crawler_version": CRAWLER_VERSION,
        "count": len(filtered_items),
        "items": filtered_items,
    }

    RAW_OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log("========== Crawl Finished ==========")
    log("Raw clean items before time filter: " + str(len(clean_all_items)))
    log("Raw items after Taiwan time filter: " + str(len(filtered_items)))
    log("Saved raw news to: " + str(RAW_OUTPUT))
    log("Output timezone: Asia/Taipei")
    log("Output generated_at: " + output["generated_at"])
    log("Output fetch_start_time: " + output["fetch_start_time"])
    log("Output fetch_end_time: " + output["fetch_end_time"])

    if latest_tw:
        log("Latest item in Taiwan time:")
        latest_item = filtered_items[0]
        log(json.dumps(latest_item, ensure_ascii=False, indent=2))

    if oldest_tw:
        log("Oldest item in Taiwan time:")
        oldest_item = filtered_items[-1]
        log(json.dumps(oldest_item, ensure_ascii=False, indent=2))

    log("===== raw_news.json preview =====")
    log("raw_news exists: " + str(RAW_OUTPUT.exists()))
    log("generated_at: " + output["generated_at"])
    log("fetch_start_time: " + output["fetch_start_time"])
    log("fetch_end_time: " + output["fetch_end_time"])
    log("timezone: " + output["timezone"])
    log("source_time_assumption: " + output["source_time_assumption"])
    log("count: " + str(output["count"]))

    if filtered_items:
        log("latest item:")
        log(json.dumps(filtered_items[0], ensure_ascii=False, indent=2))
        log("oldest item:")
        log(json.dumps(filtered_items[-1], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
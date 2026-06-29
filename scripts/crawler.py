import json
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://wallstreetcn.com/live/global"

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

    # Python weekday: Monday=0, Tuesday=1, ..., Sunday=6
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


def parse_date_line_as_tw(line, now_tw):
    """
    華爾街見聞頁面只有 06月29日 這種格式，沒有年份。
    這裡用台灣時間的年份補上。
    """

    m = DATE_RE.match(line.strip())
    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    year = now_tw.year

    dt = datetime(year, month, day, tzinfo=TW_TZ)

    # 處理跨年，例如 1月初看到 12月31日
    if dt > now_tw + timedelta(days=2):
        dt = datetime(year - 1, month, day, tzinfo=TW_TZ)

    return dt.date()


def extract_news_items(text, now_tw):
    """
    從頁面文字抽取新聞。
    Playwright context 已強制設定 timezone_id='Asia/Taipei'，
    所以頁面上看到的時間會以台灣時間渲染。
    這裡解析出來的 datetime 也一律視為台灣時間。
    """

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

        if len(headline) > 120:
            content = headline
            headline = headline[:80] + "..."

        item = {
            "datetime": current_item["datetime"],
            "headline": headline,
            "content": content,
            "source": "華爾街見聞",
            "url": URL,
            "timezone": "Asia/Taipei",
        }

        items.append(item)
        current_item = None

    for line in lines:
        d = parse_date_line_as_tw(line, now_tw)

        if d:
            flush_item()
            current_date = d
            continue

        tm = TIME_RE.match(line)

        if tm and current_date:
            flush_item()

            hour = int(tm.group(1))
            minute = int(tm.group(2))

            dt_tw = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                hour,
                minute,
                tzinfo=TW_TZ,
            )

            current_item = {
                "datetime": dt_tw.strftime("%Y-%m-%d %H:%M"),
                "lines": [],
            }

            continue

        if current_item:
            current_item["lines"].append(line)

    flush_item()

    # 去重
    seen = set()

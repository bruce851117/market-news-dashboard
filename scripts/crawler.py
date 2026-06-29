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
    頁面日期格式通常是 06月29日，沒有年份。
    這裡先用目前台灣時間的年份補上。
    後續會把頁面上的日期時間視為 UTC，再轉成台灣時間。
    """

    m = DATE_RE.match(line.strip())

    if not m:
        return None

    month = int(m.group(1))
    day = int(m.group(2))
    year = now_tw.year

    dt_utc = datetime(year, month, day, tzinfo=UTC_TZ)

    # 處理跨年，例如 1月初看到 12月31日
    if dt_utc.astimezone(TW_TZ) > now_tw + timedelta(days=2):
        dt_utc = datetime(year - 1, month, day, tzinfo=UTC_TZ)

    return dt_utc.date()


def page_datetime_utc_to_tw(date_obj, hour, minute):
    """
    頁面解析到的日期時間，視為 UTC。
    寫入 data 前轉成台灣時間。
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

    return dt_utc, dt_tw


def extract_news_items(text, now_tw):
    """
    從頁面文字抽取新聞。

    本版時間邏輯：
    - 頁面上的日期時間視為 UTC
    - 轉成 Asia/Taipei 後寫入 item["datetime"]
    - 原始 UTC 時間保留在 item["datetime_source_utc"]
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

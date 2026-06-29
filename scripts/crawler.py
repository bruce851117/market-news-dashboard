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



import json
import os
import re
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from google import genai
from google.genai import types

TZ = ZoneInfo("Asia/Taipei")

DATA_DIR = Path("data")
RAW_INPUT = DATA_DIR / "raw_news.json"
OUTPUT = DATA_DIR / "news.json"

MODEL_NAME = "gemini-3.1-flash-lite"

CATEGORY_MAP = {
    "bond": "債市",
    "equity": "股市",
    "central_bank": "央行",
    "economy": "經濟",
    "war": "戰爭",
    "commodity": "商品",
}


def log(msg):
    print(msg, flush=True)


def safe_json_loads(text):
    text = text.strip()
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def chunk_items(items, chunk_size=25):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def short_headline(headline):
    headline = str(headline or "").strip()
    headline = headline.replace("【", "").replace("】", "")
    headline = re.sub(r"\s+", " ", headline)

    if len(headline) > 30:
        headline = headline[:30]

    return headline


def fallback_filter(items):
    output = []

    for item in items:
        text = item.get("headline", "") + " " + item.get("content", "")

        category = "economy"

        if any(k in text for k in ["美债", "美債", "国债", "國債", "收益率", "殖利率", "Treasury", "利率"]):
            category = "bond"
        elif any(k in text for k in ["Fed", "FOMC", "美联储", "聯準會", "ECB", "BOJ", "BOE", "PBOC", "央行", "降息", "升息", "加息"]):
            category = "central_bank"
        elif any(k in text for k in ["股市", "美股", "A股", "港股", "纳指", "納指", "标普", "標普", "道指", "Nvidia", "英伟达", "輝達"]):
            category = "equity"
        elif any(k in text for k in ["战争", "戰爭", "冲突", "衝突", "伊朗", "以色列", "乌克兰", "烏克蘭", "俄罗斯", "俄羅斯", "制裁"]):
            category = "war"
        elif any(k in text for k in ["原油", "油价", "油價", "天然气", "天然氣", "黄金", "黃金", "铜", "銅", "OPEC"]):
            category = "commodity"


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

MODEL_NAME = "gemini-2.5-flash"

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


def safe_json_loads(text: str):
    text = text.strip()

    # 移除 markdown code block
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    # 嘗試抓 JSON array
    start = text.find("[")
    end = text.rfind("]")

    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return json.loads(text)


def chunk_items(items, chunk_size=25):
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def fallback_filter(items):
    """
    如果 Gemini 失敗，就用 Python 簡單分類。
    注意：這只是備援，正常情況仍由 Gemini 決定是否保留新聞。
    """

    output = []

    for item in items:
        text = item.get("headline", "") + " " + item.get("content", "")

        category = "economy"

        if any(k in text for k in ["美债", "美債", "国债", "國債", "收益率", "殖利率", "Treasury", "利率", "标售", "標售"]):
            category = "bond"
        elif any(k in text for k in ["Fed", "FOMC", "美联储", "聯準會", "ECB", "BOJ", "BOE", "PBOC", "央行", "降息", "升息", "加息"]):
            category = "central_bank"
        elif any(k in text for k in ["股市", "美股", "A股", "港股", "纳指", "納指", "标普", "標普", "道指", "Nvidia", "英伟达", "輝達"]):
            category = "equity"
        elif any(k in text for k in ["战争", "戰爭", "冲突", "衝突", "伊朗", "以色列", "乌克兰", "烏克蘭", "俄罗斯", "俄羅斯", "制裁"]):
            category = "war"
        elif any(k in text for k in ["原油", "油价", "油價", "天然气", "天然氣", "黄金", "黃金", "铜", "銅", "OPEC"]):
            category = "commodity"

        output.append({
            "datetime": item.get("datetime", ""),
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": 3,
            "headline": item.get("headline", ""),
            "summary": item.get("content", "")[:120],
            "tags": [],
            "source": item.get("source", "華爾街見聞"),
            "url": item.get("url", "https://wallstreetcn.com/live/global"),
        })

    return output


def summarize_with_gemini(items):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in GitHub Secrets")

    client = genai.Client(api_key=api_key)

    all_results = []

    batches = list(chunk_items(items, 25))
    total_batches = len(batches)

    log(f"Total raw items sent to Gemini: {len(items)}")
    log(f"Total Gemini batches: {total_batches}")

    for batch_no, batch in enumerate(batches, start=1):
        log(f"Summarizing batch {batch_no}/{total_batches}, items: {len(batch)}")

        prompt = f"""
你是一位全球總體經濟、利率、外匯與股票市場策略分析師，使用者是一位債券/股票交易員。

請閱讀以下華爾街見聞快訊，幫我做交易員版本的資訊整理。

任務：

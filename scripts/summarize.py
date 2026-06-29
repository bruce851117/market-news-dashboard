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


def prefilter_market_news(items):
    """
    先用關鍵字初篩，避免把所有雜訊新聞都丟給 Gemini。
    這樣可以大幅縮短 summarize 時間。
    """

    market_keywords = [
        # Rates / Bonds
        "Fed", "FOMC", "Powell", "美联储", "聯準會", "降息", "升息", "加息",
        "利率", "政策利率", "基準利率", "美债", "美債", "国债", "國債",
        "收益率", "殖利率", "Treasury", "UST", "曲线", "曲線",
        "财政部", "財政部", "标售", "標售", "拍卖", "拍賣",

        # Macro data
        "CPI", "PPI", "PMI", "GDP", "PCE", "非农", "非農", "就业", "就業",
        "失业", "失業", "薪资", "薪資", "通胀", "通膨", "物价", "物價",
        "零售销售", "零售銷售", "消费者信心", "消費者信心",
        "贸易", "貿易", "出口", "进口", "進口",

        # Central banks
        "ECB", "欧洲央行", "歐洲央行", "BOJ", "日本央行", "BOE",
        "英国央行", "英國央行", "PBOC", "人民银行", "人民銀行",
        "央行", "货币政策", "貨幣政策", "量化紧缩", "量化緊縮", "QT",

        # FX
        "美元", "人民币", "人民幣", "日元", "日圓", "欧元", "歐元",

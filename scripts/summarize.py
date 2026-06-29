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
    text = str(text or "").strip()
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


def build_news_prompt(batch):
    batch_json = json.dumps(batch, ensure_ascii=False)

    instruction = (
        "你是一位全球總體經濟、利率、外匯與股票市場策略分析師，"
        "使用者是一位債券與股票交易員。\n\n"
        "重要語言規則：\n"
        "1. 所有輸出內容一律使用繁體中文。\n"
        "2. 不要使用簡體中文。\n"
        "3. Fed、ECB、BOJ、UST、CPI、Nvidia、TSMC 等專有名詞可保留英文。\n\n"
        "請閱讀以下華爾街見聞快訊，整理成交易員版本的重要新聞。\n\n"
        "任務：\n"
        "1. 自行判斷哪些新聞重要、哪些新聞不重要。\n"
        "2. 刪除不重要新聞，不要輸出。\n"
        "3. 保留對利率、債市、股市、央行政策、總經數據、戰爭地緣政治、商品能源有影響的消息。\n\n"
        "請特別刪除以下類型新聞：\n"
        "A. 純描述價格走勢、但沒有政策、數據、事件或風險原因的新聞。\n"
        "例如：中國國債期貨早盤全線收漲、日本10年期國債收益率上升5個基點、美股期貨小幅走高。\n"
        "B. 一般性債券發行、金融債發行、農發行、國開行、進出口行發債、地方債發行等例行發債消息。\n"
        "例如：農發行發行1、2年期債券，規模共110億元。\n"
        "C. 體育、娛樂、地方社會新聞、無市場影響的小型個股消息。\n\n"
        "分類只能使用以下其中一類：\n"
        "bond：債市、利率、美債、殖利率、信用、重要財政部標售或債市政策。\n"

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
URL = "https" + "://wallstreetcn.com/live/global"

DATA_DIR = Path("data")
RAW_INPUT = DATA_DIR / "raw_news.json"
OUTPUT = DATA_DIR / "news.json"

USER_IMPORTANT_NOTES_PATHS = [
    Path("user_important_notes.txt"),
    DATA_DIR / "user_important_notes.txt",
]

MODEL_NAME = "gemini-3.1-flash-lite"

CATEGORY_MAP = {
    "bond": "債市",
    "equity": "股市",
    "central_bank": "央行",
    "economy": "經濟",
    "fiscal_policy": "財政政策",
    "war": "戰爭",
    "commodity": "商品",
}


def log(msg):
    print(msg, flush=True)


def trim_text(value, max_len):
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("【", "").replace("】", "")

    if len(text) > max_len:
        text = text[:max_len]

    return text


def short_headline(value):
    return trim_text(value, 30)


def short_summary(value):
    return trim_text(value, 90)


def short_content(value):
    return trim_text(value, 180)


def safe_json_loads(text):
    text = str(text or "").strip()
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    start = text.find("[")
    end = text.rfind("]")

    if start >= 0 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


def chunk_items(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def load_user_important_notes():
    """
    讀取使用者過去認為重要的新聞。
    支援兩個位置：
    1. repo 根目錄 user_important_notes.txt
    2. data/user_important_notes.txt

    格式：
    新聞A....
    新聞B....
    """
    for path in USER_IMPORTANT_NOTES_PATHS:
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text.strip()

            # 避免 prompt 太長，只保留最後 6000 字
            if len(text) > 6000:
                text = text[-6000:]

            log(f"Loaded user important notes from: {path}, chars={len(text)}")
            return text

    log("No user_important_notes.txt found. Continue without user preference notes.")
    return ""


def build_news_prompt(batch):
    batch_json = json.dumps(batch, ensure_ascii=False)
    prompt = ""
    prompt += "你是全球總體經濟、利率、外匯與股票市場策略分析師。\n"
    prompt += "使用者是債券與股票交易員。請用繁體中文整理快訊。不要使用簡體中文。\n"
    prompt += "專有名詞如 Fed、ECB、BOJ、UST、CPI、Nvidia、TSMC 可保留英文。\n\n"
    
    if user_important_notes:
        prompt += "以下是使用者過去認為重要的新聞範例，請將其視為使用者偏好的重要性判斷參考。\n"
        prompt += "請參考這些新聞的主題、資產類別、政策含義、交易影響與市場敏感度，判斷本次快訊的重要性。\n"
        prompt += "使用者重要新聞範例：\n"
        prompt += user_important_notes
        prompt += "\n\n"

    prompt += "請保留會影響利率、債市、股市(尤其是像某股票漲/跌多少，因為....原因的新聞)、央行、總經、財政政策、財政支出傾向或談話(尤其美國 英國 日本 歐洲，像是英国首相热门人选伯纳姆：将以公平、可持续的方式削减福利支出)、地緣政治、商品能源的新聞。\n"
    prompt += "請刪除不重要新聞、純價格走勢新聞、例行債券發行新聞、體育娛樂地方社會新聞。\n"
    prompt += "純價格走勢例子：中國國債期貨早盤全線收漲、日本10年期國債收益率上升5個基點、美股期貨小幅走高。\n"
    prompt += "例行發債例子：農發行發行1、2年期債券，規模共110億元。\n\n"
    prompt += "category 只能是 bond、equity、central_bank、fiscal_policy、economy、war、commodity。\n"
    prompt += "importance 為1到5，5代表最重要。\n"
    prompt += "headline：30個中文字以內，繁體中文。\n"
    prompt += "summary：必填，90個中文字以內，繁體中文，若原文過長再幫忙濃縮即可，不要加入你的判斷，如果有主詞也不要省略\n"
    prompt += "content：必填，180個中文字以內，繁體中文，比summary更完整。\n"
    prompt += "tags：英文或市場代號。\n"
    prompt += "只輸出 JSON array，不要 markdown，不要解釋。\n\n"
    prompt += "JSON格式："
    prompt += '[{"datetime":"2026-06-29 07:30","category":"bond","importance":5,"headline":"Fed釋出偏鷹訊號","summary":"Fed官員談話偏鷹，市場可能下修降息預期。","content":"Fed官員釋出偏鷹訊號，使短端利率與美債殖利率面臨重新定價壓力，股市風險偏好可能受抑。","tags":["Fed","UST"],"source":"華爾街見聞","url":"https://wallstreetcn.com/live/global"}]\n\n'
    prompt += "快訊資料：\n"
    prompt += batch_json
    return prompt


def build_brief_prompt(items):
    items_json = json.dumps(items, ensure_ascii=False)

    prompt = ""
    prompt += "你是全球總體經濟與跨資產策略分析師。請用繁體中文。不要使用簡體中文。\n"
    prompt += "以下是已篩選的重要市場新聞，請整理成交易員晨報重點。\n"
    prompt += "請輸出5到10點，每點不超過55個中文字，不要加入自己的想法，以原文內的事實呈現。\n"
    prompt += "只輸出 JSON array of strings，不要 markdown，不要解釋。\n"
    prompt += '格式例子：["Fed官員偏鷹，短端利率降息定價可能受壓。","中東風險升溫，油價風險溢價仍需關注。"]\n\n'
    prompt += "重要新聞：\n"
    prompt += items_json

    return prompt


def fallback_filter(items):
    output = []

    for item in items:
        text = item.get("headline", "") + " " + item.get("content", "")
        category = "economy"

        if any(k in text for k in ["美債", "國債", "收益率", "殖利率", "Treasury", "利率"]):
            category = "bond"
        elif any(k in text for k in ["Fed", "FOMC", "聯準會", "美聯儲", "ECB", "BOJ", "BOE", "PBOC", "央行"]):
            category = "central_bank"
        elif any(k in text for k in [
            "財政", "财政", "預算", "预算", "赤字", "政府支出", "公共支出",
            "減稅", "减税", "增稅", "增税", "稅改", "税改", "補貼", "补贴",
            "國債發行", "国债发行", "債務上限", "债务上限", "財政部", "财政部",
            "Treasury", "tariff", "關稅", "关税", "刺激方案", "財政刺激", "财政刺激"
        ]):
            category = "fiscal_policy"
        elif any(k in text for k in ["股市", "美股", "A股", "港股", "納指", "標普", "道指", "Nvidia", "輝達"]):
            category = "equity"
        elif any(k in text for k in ["戰爭", "衝突", "伊朗", "以色列", "烏克蘭", "俄羅斯", "制裁"]):
            category = "war"
        elif any(k in text for k in ["原油", "油價", "天然氣", "黃金", "銅", "OPEC"]):
            category = "commodity"

        headline = short_headline(item.get("headline", ""))
        raw_content = item.get("content", "")
        summary = short_summary(raw_content) or headline
        content = short_content(raw_content) or summary

        output.append({
            "datetime": item.get("datetime", ""),
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": 3,
            "headline": headline,
            "summary": summary,
            "content": content,
            "tags": [],
            "source": "華爾街見聞",
            "url": URL,
        })

    return output


def normalize_results(results):
    cleaned = []
    valid_categories = set(CATEGORY_MAP.keys())

    for item in results:
        if not isinstance(item, dict):
            continue

        category = item.get("category", "economy")


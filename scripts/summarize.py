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
USER_IMPORTANT_NOTES = DATA_DIR / "user_important_notes.txt"
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
    if not USER_IMPORTANT_NOTES.exists():
        return ""

    text = USER_IMPORTANT_NOTES.read_text(encoding="utf-8").strip()
    if not text:
        return ""

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line)

    return "\n".join(lines)


def build_user_important_notes_section(user_important_notes):
    if not user_important_notes:
        return "目前沒有使用者手動標記的重要新聞。"

    return user_important_notes


def build_news_prompt(batch, user_important_notes=""):
    batch_json = json.dumps(batch, ensure_ascii=False)
    important_notes_text = build_user_important_notes_section(user_important_notes)

    prompt = ""
    prompt += "你是全球總體經濟、利率、外匯與股票市場策略分析師。\n"
    prompt += "使用者是債券與股票交易員。請用繁體中文整理快訊。不要使用簡體中文。\n"
    prompt += "專有名詞如 Fed、ECB、BOJ、UST、CPI、Nvidia、TSMC 可保留英文。\n\n"

    prompt += "以下是使用者過去手動標記為重要的新聞或市場主題，請視為使用者近期關注的交易主線。\n"
    prompt += "如果今日新聞與這些主題相關，請提高重要性排序，並在 summary 或 content 中自然點出其市場意義。\n"
    prompt += "但不得捏造未出現在原始快訊中的資訊，也不要硬把無關新聞連結到使用者關注主題。\n\n"
    prompt += "【使用者重要新聞】\n"
    prompt += important_notes_text
    prompt += "\n\n"

    prompt += "請保留會影響利率、債市、股市、央行、總經、財政政策、財政支出傾向或談話，尤其是美國、英國、日本、歐洲相關內容，例如英國首相熱門人選表示將以公平、可持續方式削減福利支出。\n"
    prompt += "請保留會影響地緣政治、戰爭風險、商品能源、半導體、AI供應鏈、主要科技股、台股與全球風險偏好的新聞。\n"
    prompt += "請刪除不重要新聞、純價格走勢新聞、例行債券發行新聞、體育娛樂地方社會新聞。\n"
    prompt += "純價格走勢例子：中國國債期貨早盤全線收漲、日本10年期國債收益率上升5個基點、美股期貨小幅走高。\n"
    prompt += "例行發債例子：農發行發行1、2年期債券，規模共110億元。\n\n"

    prompt += "category 只能是 bond、equity、central_bank、fiscal_policy、economy、war、commodity。\n"
    prompt += "importance 為1到5，5代表最重要。\n"
    prompt += "如果新聞與使用者重要新聞高度相關，importance 可以提高，但仍需根據市場影響力判斷。\n"
    prompt += "headline：30個中文字以內，繁體中文。\n"
    prompt += "summary：必填，90個中文字以內，繁體中文，說明市場或交易意義。如果原文有明確主詞，請保留主詞。例如 A表示：\n"
    prompt += "content：必填，180個中文字以內，繁體中文，比summary更完整。\n"
    prompt += "tags：英文或市場代號。\n"
    prompt += "只輸出 JSON array，不要 markdown，不要解釋。\n\n"

    prompt += "JSON格式：\n"
    prompt += '[{"datetime":"2026-06-29 07:30","category":"bond","importance":5,"headline":"Fed釋出偏鷹訊號","summary":"Fed官員談話偏鷹，市場可能下修降息預期。","content":"Fed官員釋出偏鷹訊號，使短端利率與美債殖利率面臨重新定價壓力，股市風險偏好可能受抑。","tags":["Fed","UST"],"source":"華爾街見聞","url":"https://wallstreetcn.com/live/global"}]\n\n'

    prompt += "快訊資料：\n"
    prompt += batch_json
    return prompt


def build_brief_prompt(items, user_important_notes=""):
    items_json = json.dumps(items, ensure_ascii=False)
    important_notes_text = build_user_important_notes_section(user_important_notes)

    prompt = ""
    prompt += "你是全球總體經濟與跨資產策略分析師。請用繁體中文。不要使用簡體中文。\n"
    prompt += "以下是已篩選的重要市場新聞，請整理成交易員晨報重點。\n\n"

    prompt += "以下是使用者過去手動標記為重要的新聞或市場主題，請視為使用者近期關注的交易主線。\n"
    prompt += "若今日重要新聞延續這些主題，請在晨報重點中提高排序，但不得捏造沒有出現在新聞中的資訊。\n\n"
    prompt += "【使用者重要新聞】\n"
    prompt += important_notes_text
    prompt += "\n\n"

    prompt += "請輸出5到10點，每點不超過55個中文字，聚焦市場意義，不要只是複製標題。\n"
    prompt += "只輸出 JSON array of strings，不要 markdown，不要解釋。\n"
    prompt += "格式例子：[\"Fed官員偏鷹，短端利率降息定價可能受壓。\",\"中東風險升溫，油價風險溢價仍需關注。\"]\n\n"
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

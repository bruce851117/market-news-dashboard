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

        output.append({
            "datetime": item.get("datetime", ""),
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": 3,
            "headline": short_headline(item.get("headline", "")),
            "summary": "",
            "tags": [],
            "source": item.get("source", "華爾街見聞"),
            "url": item.get("url", "https://wallstreetcn.com/live/global"),
        })

    return output


def build_prompt(batch):
    batch_json = json.dumps(batch, ensure_ascii=False)

    prompt_lines = [
        "你是一位全球總體經濟、利率、外匯與股票市場策略分析師，使用者是一位債券/股票交易員。",
        "",
        "請閱讀以下華爾街見聞快訊，幫我做交易員版本的資訊整理。",
        "",
        "任務：",
        "1. 你會看到完整快訊資料，請自行判斷哪些新聞重要、哪些新聞不重要。",
        "2. 刪除不重要資訊，不要輸出那些新聞。",
        "3. 保留對利率、債市、股市、央行政策、總經數據、戰爭地緣政治、商品能源有影響的消息。",
        "",
        "請特別刪除以下類型新聞：",
        "A. 純描述價格走勢、但沒有政策、數據、事件或風險原因的新聞。",
        "   例如：中國國債期貨早盤全線收漲、日本10年期國債收益率上升5個基點、美股期貨小幅走高。",
        "B. 一般性債券發行、金融債發行、農發行/國開行/進出口行發債、地方債發行等例行發債消息。",
        "   例如：農發行發行1、2年期債券，規模共110億元。",
        "C. 體育、娛樂、地方社會新聞、無市場影響的小型個股消息。",
        "",
        "分類只能使用以下其中一類：",
        "- bond：債市、利率、美債、殖利率、信用、重要財政部標售或債市政策",
        "- equity：股市、重大企業財報、科技龍頭、AI供應鏈、主要股指",
        "- central_bank：Fed、ECB、BOJ、BOE、PBOC、央行官員談話、升降息",
        "- economy：CPI、PPI、PMI、GDP、就業、薪資、消費、貿易、財政政策、關稅",
        "- war：戰爭、地緣政治、制裁、中東、俄烏、台海、軍事衝突",
        "- commodity：原油、天然氣、黃金、銅、農產品、能源供應",
        "",
        "每則新聞給 importance，1到5分：",
        "- 5：高度影響全球利率、股市、FX、油價，例如FOMC、CPI、重大就業數據、戰爭升級、重大央行政策",
        "- 4：重要市場新聞",
        "- 3：中等重要",
        "- 2：低重要但仍可保留",
        "- 1：通常應刪除",
        "",
        "輸出要求：",
        "1. headline 請簡化成30個中文字以內，保留市場重點，不要扭曲原意。",
        "2. summary 可以留空字串，但欄位必須存在。",
        "3. tags 用英文或常用市場代號，例如 Fed、UST、CPI、Oil、ECB、China、A-share、AI。",
        "4. 如果新聞不重要，請不要輸出該則新聞。",
        "5. 請務必只輸出 JSON array，不要加解釋，不要 markdown。",
        "",
        "輸出格式如下：",
        "[",
        "  {",
        "    \"datetime\": \"2026-06-29 07:30\",",
        "    \"category\": \"bond\",",
        "    \"importance\": 5,",
        "    \"headline\": \"Fed釋出偏鷹訊號\",",
        "    \"summary\": \"\",",
        "    \"tags\": [\"Fed\", \"UST\"],",
        "    \"source\": \"華爾街見聞\",",
        "    \"url\": \"https://wallstreetcn.com/live/global\"",
        "  }",
        "]",
        "",
        "以下是快訊資料：",
        batch_json
    ]

    return "\n".join(prompt_lines)


def summarize_with_gemini(items):

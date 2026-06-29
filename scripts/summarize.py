
import json
import os
import re
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


def safe_json_loads(text: str):
    text = text.strip()

    # 移除 markdown code block
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    # 嘗試抓第一個 JSON array
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    return json.loads(text)


def chunk_items(items, chunk_size=60):
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def fallback_filter(items):
    important_keywords = [
        "Fed", "FOMC", "Powell", "美联储", "聯準會", "降息", "升息", "利率",
        "美债", "美債", "国债", "國債", "收益率", "殖利率", "Treasury",
        "CPI", "PPI", "PMI", "GDP", "非农", "非農", "就业", "就業", "通胀", "通膨",
        "ECB", "欧洲央行", "歐洲央行", "BOJ", "日本央行", "BOE", "英国央行", "英國央行",
        "PBOC", "人民银行", "人民銀行", "央行",
        "美元", "人民币", "人民幣", "日元", "日圓", "欧元", "歐元",
        "股市", "美股", "A股", "港股", "日股", "台股", "纳指", "標普", "道指",
        "战争", "戰爭", "冲突", "衝突", "伊朗", "以色列", "乌克兰", "烏克蘭",
        "俄罗斯", "俄羅斯", "制裁", "关税", "關稅",
        "原油", "油价", "油價", "天然气", "天然氣", "黄金", "黃金",
    ]

    output = []
    for item in items:
        text = item.get("headline", "") + " " + item.get("content", "")
        if not any(k in text for k in important_keywords):
            continue

        category = "economy"
        if any(k in text for k in ["美债", "美債", "国债", "國債", "收益率", "殖利率", "Treasury", "利率"]):
            category = "bond"
        elif any(k in text for k in ["Fed", "FOMC", "美联储", "聯準會", "ECB", "BOJ", "BOE", "PBOC", "央行"]):
            category = "central_bank"
        elif any(k in text for k in ["股市", "美股", "A股", "港股", "纳指", "標普", "道指"]):
            category = "equity"
        elif any(k in text for k in ["战争", "戰爭", "冲突", "衝突", "伊朗", "以色列", "乌克兰", "烏克蘭", "俄罗斯", "俄羅斯"]):
            category = "war"
        elif any(k in text for k in ["原油", "油价", "油價", "天然气", "天然氣", "黄金", "黃金"]):
            category = "commodity"

        output.append({
            "datetime": item["datetime"],
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": 3,
            "headline": item["headline"],
            "summary": item.get("content", "")[:120],
            "tags": [],
            "source": item.get("source", "華爾街見聞"),
            "url": item.get("url", ""),
        })

    return output


def summarize_with_gemini(items):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in GitHub Secrets")

    client = genai.Client(api_key=api_key)

    all_results = []

    for batch_no, batch in enumerate(chunk_items(items, 60), start=1):
        print(f"Summarizing batch {batch_no}, items: {len(batch)}")

        prompt = f"""
你是一位全球總體經濟、利率、外匯與股票市場策略分析師，使用者是一位債券/股票交易員。

請閱讀以下華爾街見聞快訊，幫我做交易員版本的資訊整理。

任務：
1. 刪除不重要資訊。
2. 保留對利率、債市、股市、央行政策、總經數據、戰爭地緣政治、商品能源有影響的消息。
3. 將新聞分類成以下其中一類：
   - bond：債市、利率、美債、殖利率、信用、財政部標售
   - equity：股市、重大企業財報、科技龍頭、AI供應鏈、主要股指
   - central_bank：Fed、ECB、BOJ、BOE、PBOC、央行官員談話、升降息
   - economy：CPI、PPI、PMI、GDP、就業、薪資、消費、貿易、財政政策、關稅
   - war：戰爭、地緣政治、制裁、中東、俄烏、台海、軍事衝突
   - commodity：原油、天然氣、黃金、銅、農產品、能源供應

4. 每則新聞給重要度 importance，1到5分：
   - 5：高度影響全球利率/股市/FX/油價，例如FOMC、CPI、戰爭升級、重大央行政策
   - 4：重要市場新聞
   - 3：中等重要
   - 2：低重要但仍可保留
   - 1：通常應刪除

5. summary 用繁體中文，不超過80字，要站在交易員角度描述市場意義。
6. tags 用英文或常用市場代號，例如 Fed、UST、CPI、Oil、ECB、China、A-share、AI。

請務必只輸出 JSON array，不要加解釋，不要 markdown。

輸出格式：
[
  {{
    "datetime": "2026-06-29 07:30",
    "category": "bond",
    "importance": 5,
    "headline": "原始新聞標題或精簡標題",
    "summary": "繁體中文摘要",
    "tags": ["Fed", "UST"],
    "source": "華爾街見聞",
    "url": "https://wallstreetcn.com/live/global"
  }}
]

以下是快訊資料：
{json.dumps(batch, ensure_ascii=False)}
"""

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        text = response.text
        parsed = safe_json_loads(text)

        if isinstance(parsed, list):
            all_results.extend(parsed)

    return all_results


def normalize_results(results):
    cleaned = []

    valid_categories = set(CATEGORY_MAP.keys())

    for item in results:
        if not isinstance(item, dict):
            continue

        category = item.get("category", "economy")
        if category not in valid_categories:
            category = "economy"

        importance = item.get("importance", 3)
        try:
            importance = int(importance)
        except Exception:
            importance = 3

        importance = max(1, min(5, importance))

        cleaned.append({
            "datetime": item.get("datetime", ""),
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": importance,
            "headline": item.get("headline", "").strip(),
            "summary": item.get("summary", "").strip(),
            "tags": item.get("tags", []),
            "source": item.get("source", "華爾街見聞"),
            "url": item.get("url", "https://wallstreetcn.com/live/global"),
        })

    # 移除空標題
    cleaned = [x for x in cleaned if x["datetime"] and x["headline"]]

    # 去重
    seen = set()
    unique = []
    for item in cleaned:
        key = (item["datetime"], item["headline"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    unique.sort(key=lambda x: x["datetime"], reverse=True)
    return unique


def main():
    raw = json.loads(RAW_INPUT.read_text(encoding="utf-8"))
    items = raw.get("items", [])

    print(f"Loaded raw items: {len(items)}")

    try:
        results = summarize_with_gemini(items)
        results = normalize_results(results)
        print(f"Gemini summarized items: {len(results)}")
    except Exception as e:
        print(f"Gemini failed, using fallback filter. Error: {e}")
        results = fallback_filter(items)
        results = normalize_results(results)

    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")

    output = {
        "generated_at": now,
        "timezone": "Asia/Taipei",
        "source": "https://wallstreetcn.com/live/global",
        "count": len(results),
        "categories": CATEGORY_MAP,
        "items": results,
    }

    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved summarized news to {OUTPUT}")


if __name__ == "__main__":
    main()

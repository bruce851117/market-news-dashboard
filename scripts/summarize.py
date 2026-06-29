import json
import os
import re
import time
from pathlib import Path
from datetime import = DATA_DIR / "news.json"from datetime import datetime

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


def clean_url(url):
    url = str(url or "").strip()

    if "wallstreetcn.com/live/global" in url:
        return "https://wallstreetcn.com/live/global"

    return url


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


def short_text(text, max_len):
    text = str(text or "").strip()
    text = text.replace("【", "").replace("】", "")
    text = re.sub(r"\s+", " ", text)

    if len(text) > max_len:
        text = text[:max_len]

    return text


def short_headline(headline):
    return short_text(headline, 30)


def short_summary(summary):
    return short_text(summary, 90)


def short_content(content):
    return short_text(content, 180)


def build_news_prompt(batch):
    batch_json = json.dumps(batch, ensure_ascii=False)

    prompt = ""
    prompt += "你是一位全球總體經濟、利率、外匯與股票市場策略分析師，使用者是一位債券與股票交易員。\n\n"
    prompt += "重要語言規則：\n"
    prompt += "1. 所有輸出內容一律使用繁體中文。\n"
    prompt += "2. 不要使用簡體中文。\n"
    prompt += "3. Fed、ECB、BOJ、UST、CPI、Nvidia、TSMC 等專有名詞可保留英文。\n\n"

    prompt += "請閱讀以下華爾街見聞快訊，整理成交易員版本的重要新聞。\n\n"
    prompt += "任務：\n"
    prompt += "1. 自行判斷哪些新聞重要、哪些新聞不重要。\n"
    prompt += "2. 刪除不重要新聞，不要輸出。\n"
    prompt += "3. 保留對利率、債市、股市、央行政策、總經數據、戰爭地緣政治、商品能源有影響的消息。\n\n"

    prompt += "請特別刪除以下類型新聞：\n"
    prompt += "A. 純描述價格走勢、但沒有政策、數據、事件或風險原因的新聞。\n"
    prompt += "例如：中國國債期貨早盤全線收漲、日本10年期國債收益率上升5個基點、美股期貨小幅走高。\n"
    prompt += "B. 一般性債券發行、金融債發行、農發行、國開行、進出口行發債、地方債發行等例行發債消息。\n"
    prompt += "例如：農發行發行1、2年期債券，規模共110億元。\n"
    prompt += "C. 體育、娛樂、地方社會新聞、無市場影響的小型個股消息。\n\n"

    prompt += "分類只能使用以下其中一類：\n"
    prompt += "bond：債市、利率、美債、殖利率、信用、重要財政部標售或債市政策。\n"
    prompt += "equity：股市、重大企業財報、科技龍頭、AI供應鏈、主要股指。\n"
    prompt += "central_bank：Fed、ECB、BOJ、BOE、PBOC、央行官員談話、升降息。\n"
    prompt += "economy：CPI、PPI、PMI、GDP、就業、薪資、消費、貿易、財政政策、關稅。\n"
    prompt += "war：戰爭、地緣政治、制裁、中東、俄烏、台海、軍事衝突。\n"
    prompt += "commodity：原油、天然氣、黃金、銅、農產品、能源供應。\n\n"

    prompt += "importance 評分規則：\n"
    prompt += "5 = 高度影響全球利率、股市、FX、油價，例如 FOMC、CPI、重大就業數據、戰爭升級、重大央行政策。\n"
    prompt += "4 = 重要市場新聞。\n"
    prompt += "3 = 中等重要。\n"
    prompt += "2 = 低重要但仍可保留。\n"
    prompt += "1 = 通常應刪除。\n\n"

    prompt += "輸出要求：\n"
    prompt += "1. headline 必須填寫，請簡化成30個中文字以內，使用繁體中文，不扭曲原意。\n"
    prompt += "2. summary 必須填寫，使用繁體中文，不超過90個中文字，說明這則新聞對市場或交易的意義。\n"
    prompt += "3. content 必須填寫，使用繁體中文，不超過180個中文字，比 summary 更完整，可包含原新聞重點與市場影響。\n"
    prompt += "4. tags 用英文或常用市場代號，例如 Fed、UST、CPI、Oil、ECB、China、A-share、AI。\n"
    prompt += "5. 如果新聞不重要，請不要輸出該則新聞。\n"
    prompt += "6. 請務必只輸出 JSON array，不要加解釋，不要 markdown。\n\n"

    prompt += "輸出格式範例：\n"
    prompt += "[{\"datetime\":\"2026-06-29 07:30\",\"category\":\"bond\",\"importance\":5,\"headline\":\"Fed釋出偏鷹訊號\",\"summary\":\"Fed官員談話偏鷹，市場可能下修降息預期。\",\"content\":\"Fed官員釋出偏鷹訊號，使短端利率與美債殖利率面臨重新定價壓力，股市風險偏好可能受抑。\",\"tags\":[\"Fed\",\"UST\"],\"source\":\"華爾街見聞\",\"url\":\"https://wallstreetcn.com/live/global\"}]\n\n"

    prompt += "以下是快訊資料：\n"
    prompt += batch_json

    return prompt


def build_brief_prompt(items):
    items_json = json.dumps(items, ensure_ascii=False)

    prompt = ""
    prompt += "你是一位全球總體經濟、利率、外匯與股票市場策略分析師，使用者是一位債券與股票交易員。\n\n"
    prompt += "以下是已經篩選過的重要市場新聞。請整理成交易員早上可以快速閱讀的重點摘要。\n\n"
    prompt += "重要語言規則：\n"
    prompt += "1. 所有輸出內容一律使用繁體中文。\n"
    prompt += "2. 不要使用簡體中文。\n"
    prompt += "3. Fed、ECB、BOJ、UST、CPI、Nvidia、TSMC 等專有名詞可保留英文。\n\n"

    prompt += "請依照以下規則：\n"
    prompt += "1. 請輸出5到10點。\n"
    prompt += "2. 每點不超過55個中文字。\n"
    prompt += "3. 請聚焦市場意義，不要只是複製標題。\n"
    prompt += "4. 優先整理對利率、股市、央行、總經、戰爭地緣政治、商品能源影響最大的重點。\n"
    prompt += "5. 不要輸出不重要、重複或純價格波動資訊。\n"
    prompt += "6. 請務必只輸出 JSON array of strings，不要加解釋，不要 markdown。\n\n"

    prompt += "輸出格式範例：\n"
    prompt += "[\"Fed官員偏鷹，短端利率降息定價可能受壓。\",\"中東風險升溫，油價風險溢價仍需關注。\"]\n\n"
    prompt += "以下是重要新聞：\n"
    prompt += items_json

    return prompt


def fallback_filter(items):
    output = []

    for item in items:
        text = item.get("headline", "") + " " + item.get("content", "")

        category = "economy"

        if any(k in text for k in ["美債", "國債", "收益率", "殖利率", "Treasury", "利率"]):
            category = "bond"
        elif any(k in text for k in ["Fed", "FOMC", "美聯儲", "聯準會", "ECB", "BOJ", "BOE", "PBOC", "央行", "降息", "升息"]):
            category = "central_bank"
        elif any(k in text for k in ["股市", "美股", "A股", "港股", "納指", "標普", "道指", "Nvidia", "英偉達", "輝達"]):
            category = "equity"
        elif any(k in text for k in ["戰爭", "衝突", "伊朗", "以色列", "烏克蘭", "俄羅斯", "制裁"]):
            category = "war"
        elif any(k in text for k in ["原油", "油價", "天然氣", "黃金", "銅", "OPEC"]):
            category = "commodity"

        raw_content = item.get("content", "")
        fallback_summary = short_summary(raw_content)

        if not fallback_summary:
            fallback_summary = short_headline(item.get("headline", ""))

        output.append({
            "datetime": item.get("datetime", ""),
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": 3,
            "headline": short_headline(item.get("headline", "")),
            "summary": fallback_summary,
            "content": short_content(raw_content or item.get("headline", "")),
            "tags": [],
            "source": "華爾街見聞",
            "url": "https://wallstreetcn.com/live/global",
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

    log(f"Using model: {MODEL_NAME}")
    log(f"Total raw items sent to Gemini: {len(items)}")
    log(f"Total Gemini batches: {total_batches}")

    for batch_no, batch in enumerate(batches, start=1):
        log(f"Summarizing batch {batch_no}/{total_batches}, items: {len(batch)}")

        prompt = build_news_prompt(batch)

        for attempt in range(1, 3):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )

                parsed = safe_json_loads(response.text)

                if isinstance(parsed, list):
                    all_results.extend(parsed)
                    log(f"Batch {batch_no}/{total_batches} done. Returned items: {len(parsed)}")
                    break

                log(f"Batch {batch_no} returned non-list JSON.")

            except Exception as e:
                log(f"Batch {batch_no} attempt {attempt} failed: {e}")

                if attempt < 2:
                    log("Retrying after 5 seconds...")
                    time.sleep(5)
                else:
                    log(f"Batch {batch_no} failed after retries. Skipping this batch.")

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

        try:
            importance = int(item.get("importance", 3))
        except Exception:
            importance = 3

        importance = max(1, min(5, importance))

        tags = item.get("tags", [])

        if not isinstance(tags, list):
            tags = []

        headline = short_headline(item.get("headline", ""))
        summary = short_summary(item.get("summary", ""))
        content = short_content(item.get("content", ""))

        if not summary:
            summary = headline

        if not content:
            content = summary

        cleaned.append({
            "datetime": item.get("datetime", "").strip(),
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": importance,
            "headline": headline,
            "summary": summary,
            "content": content,
            "tags": tags,
            "source": "華爾街見聞",
            "url": "https://wallstreetcn.com/live/global",
        })

    cleaned = [x for x in cleaned if x["datetime"] and x["headline"]]

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


def fallback_brief_points(items):
    if not items:
        return []

    sorted_items = sorted(
        items,
        key=lambda x: (int(x.get("importance", 3)), x.get("datetime", "")),
        reverse=True,
    )

    points = []

    for item in sorted_items[:10]:
        category_name = item.get("category_name", "")
        summary = item.get("summary", "")
        headline = short_headline(item.get("headline", ""))

        if summary:
            points.append(category_name + "：" + summary)
        else:
            points.append(category_name + "：" + headline)

    return points[:10]


def generate_brief_points(items):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in GitHub Secrets")

    if not items:
        return []

    client = genai.Client(api_key=api_key)

    sorted_items = sorted(
        items,
        key=lambda x: (int(x.get("importance", 3)), x.get("datetime", "")),
        reverse=True,
    )

    brief_source_items = sorted_items[:80]
    prompt = build_brief_prompt(brief_source_items)

    log(f"Generating brief points from {len(brief_source_items)} important items...")

    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )

            parsed = safe_json_loads(response.text)

            if isinstance(parsed, list):
                points = []

                for x in parsed:
                    if isinstance(x, str):
                        text = x.strip()
                    elif isinstance(x, dict):
                        text = str(x.get("point", "")).strip()
                    else:
                        text = ""

                    if text:
                        points.append(text)

                points = points[:10]
                log(f"Brief points generated: {len(points)}")
                return points

            log("Brief response is not a list.")

        except Exception as e:
            log(f"Brief attempt {attempt} failed: {e}")

            if attempt < 2:
                log("Retrying brief after 5 seconds...")
                time.sleep(5)

    log("Brief generation failed. Using fallback brief.")
    return fallback_brief_points(items)


def main():
    log("========== Summarize Start ==========")

    if not RAW_INPUT.exists():
        raise FileNotFoundError("data/raw_news.json not found. Please run crawler.py first.")

    raw = json.loads(RAW_INPUT.read_text(encoding="utf-8"))
    items = raw.get("items", [])

    log(f"Loaded raw items: {len(items)}")
    log("No prefilter is applied. All raw items will be sent to Gemini in batches.")

    if len(items) == 0:
        output = {
            "generated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
            "timezone": "Asia/Taipei",
            "source": "https://wallstreetcn.com/live/global",
            "fetch_start_time": raw.get("fetch_start_time", ""),
            "fetch_end_time": raw.get("fetch_end_time", ""),
            "raw_count": 0,

from zoneinfo import ZoneInfo

from google import genai
from google.genai import types


TZ = ZoneInfo("Asia/Taipei")

DATA_DIR = Path("data")
RAW_INPUT = DATA_DIR / "raw_news.json"

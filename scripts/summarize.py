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


def build_news_prompt(batch):
    batch_json = json.dumps(batch, ensure_ascii=False)
    prompt = ""
    prompt += "你是全球總體經濟、利率、外匯與股票市場策略分析師。\n"
    prompt += "使用者是債券與股票交易員。請用繁體中文整理快訊。不要使用簡體中文。\n"
    prompt += "專有名詞如 Fed、ECB、BOJ、UST、CPI、Nvidia、TSMC 可保留英文。\n\n"
    prompt += "請保留會影響利率、債市、股市、央行、總經、地緣政治、商品能源的新聞。\n"
    prompt += "請刪除不重要新聞、純價格走勢新聞、例行債券發行新聞、體育娛樂地方社會新聞。\n"
    prompt += "純價格走勢例子：中國國債期貨早盤全線收漲、日本10年期國債收益率上升5個基點、美股期貨小幅走高。\n"
    prompt += "例行發債例子：農發行發行1、2年期債券，規模共110億元。\n\n"
    prompt += "category 只能是 bond、equity、central_bank、economy、war、commodity。\n"
    prompt += "importance 為1到5，5代表最重要。\n"
    prompt += "headline：30個中文字以內，繁體中文。\n"
    prompt += "summary：必填，90個中文字以內，繁體中文，說明市場或交易意義。\n"
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
        summary = short_summary(item.get("summary", "")) or headline
        content = short_content(item.get("content", "")) or summary

        cleaned.append({
            "datetime": str(item.get("datetime", "")).strip(),
            "category": category,
            "category_name": CATEGORY_MAP.get(category, category),
            "importance": importance,
            "headline": headline,
            "summary": summary,
            "content": content,
            "tags": tags,
            "source": "華爾街見聞",
            "url": URL,
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


def call_gemini_json(client, prompt, temperature):
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=temperature,
        ),
    )
    return safe_json_loads(response.text)


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
                parsed = call_gemini_json(client, prompt, 0.1)
                if isinstance(parsed, list):
                    all_results.extend(parsed)
                    log(f"Batch {batch_no}/{total_batches} done. Returned items: {len(parsed)}")
                    break
                log(f"Batch {batch_no} returned non-list JSON.")
            except Exception as e:
                log(f"Batch {batch_no} attempt {attempt} failed: {e}")
                if attempt < 2:
                    time.sleep(5)
                else:
                    log(f"Batch {batch_no} failed after retries. Skipping this batch.")
    return all_results


def fallback_brief_points(items):
    sorted_items = sorted(items, key=lambda x: (int(x.get("importance", 3)), x.get("datetime", "")), reverse=True)
    points = []
    for item in sorted_items[:10]:
        category_name = item.get("category_name", "")
        summary = item.get("summary", "")
        headline = item.get("headline", "")
        points.append(category_name + "：" + (summary or headline))
    return points[:10]


def generate_brief_points(items):
    if not items:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in GitHub Secrets")

    client = genai.Client(api_key=api_key)
    sorted_items = sorted(items, key=lambda x: (int(x.get("importance", 3)), x.get("datetime", "")), reverse=True)
    brief_source_items = sorted_items[:80]
    prompt = build_brief_prompt(brief_source_items)
    log(f"Generating brief points from {len(brief_source_items)} important items...")

    for attempt in range(1, 3):
        try:
            parsed = call_gemini_json(client, prompt, 0.2)
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
                log(f"Brief points generated: {len(points[:10])}")
                return points[:10]
            log("Brief response is not a list.")
        except Exception as e:
            log(f"Brief attempt {attempt} failed: {e}")
            if attempt < 2:
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
            "source": URL,
            "fetch_start_time": raw.get("fetch_start_time", ""),
            "fetch_end_time": raw.get("fetch_end_time", ""),
            "raw_count": 0,
            "count": 0,
            "categories": CATEGORY_MAP,
            "brief_points": [],
            "items": [],
        }
        OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        log("Saved empty summarized news.")
        return

    try:
        log("Calling Gemini for classified news...")
        results = summarize_with_gemini(items)
        results = normalize_results(results)
        log(f"Gemini summarized items: {len(results)}")
    except Exception as e:
        log(f"Gemini failed, using fallback filter. Error: {e}")
        results = fallback_filter(items)
        results = normalize_results(results)
        log(f"Fallback summarized items: {len(results)}")

    try:
        brief_points = generate_brief_points(results)
    except Exception as e:
        log(f"Brief generation failed, using fallback. Error: {e}")
        brief_points = fallback_brief_points(results)

    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    output = {
        "generated_at": now,
        "timezone": "Asia/Taipei",
        "source": URL,
        "fetch_start_time": raw.get("fetch_start_time", ""),
        "fetch_end_time": raw.get("fetch_end_time", ""),
        "raw_count": raw.get("count", len(items)),
        "count": len(results),
        "categories": CATEGORY_MAP,
        "brief_points": brief_points,
        "items": results,
    }

    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    log("========== Summarize Finished ==========")
    log(f"Saved summarized news to: {OUTPUT}")
    log(f"Final summarized items: {len(results)}")
    log(f"Brief points: {len(brief_points)}")

    if brief_points:
        log("Brief preview:")
        log(json.dumps(brief_points, ensure_ascii=False, indent=2))

    if results:
        log("Latest summarized item:")
        log(json.dumps(results[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

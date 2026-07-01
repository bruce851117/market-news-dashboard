import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


TZ = ZoneInfo("Asia/Taipei")

DATA_DIR = Path("data")
NEWS_INPUT = DATA_DIR / "news.json"
NEWS_OUTPUT = DATA_DIR / "news.json"

TICKERS = {
    "UST10Y": {
        "ticker": "^TNX",
        "label": "10Y美債殖利率",
        "type": "yield",
    },
    "ES": {
        "ticker": "ES=F",
        "label": "S&P500期貨",
        "type": "future",
    },
    "NQ": {
        "ticker": "NQ=F",
        "label": "Nasdaq期貨",
        "type": "future",
    },
}

INTERVAL = "1m"
PERIOD = "5d"

# 如果新聞時間與下一筆價格差太久，就視為沒有可用資料
MAX_GAP_MINUTES = 15


def log(msg):
    print(msg, flush=True)


def parse_news_datetime(value):
    if not value:
        return None

    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    except Exception:
        return None


def safe_float(value):
    try:
        if value is None:
            return None

        if isinstance(value, float) and math.isnan(value):
            return None

        return float(value)
    except Exception:
        return None


def fetch_price_series(ticker):
    log(f"Fetching yfinance data: {ticker}, period={PERIOD}, interval={INTERVAL}")

    df = yf.download(
        tickers=ticker,
        period=PERIOD,
        interval=INTERVAL,
        auto_adjust=False,
        prepost=True,
        progress=False,
        threads=False,
    )

    if df is None or df.empty:
        log(f"No yfinance data returned for {ticker}")
        return pd.DataFrame()

    # yfinance 單 ticker 有時仍可能回傳 MultiIndex columns，這裡統一處理
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.get_level_values(-1):
            df = df.xs(ticker, level=-1, axis=1)
        elif ticker in df.columns.get_level_values(0):
            df = df.xs(ticker, level=0, axis=1)

    if "Close" not in df.columns:
        log(f"No Close column for {ticker}")
        return pd.DataFrame()

    df = df[["Close"]].copy()
    df = df.dropna(subset=["Close"])

    if df.empty:
        log(f"Close series is empty for {ticker}")
        return pd.DataFrame()

    # yfinance index 通常帶 timezone；統一轉 Asia/Taipei
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(TZ)
    else:
        df.index = df.index.tz_convert(TZ)

    df = df.sort_index()

    log(
        f"{ticker} rows={len(df)}, "
        f"first={df.index[0].strftime('%Y-%m-%d %H:%M')}, "
        f"last={df.index[-1].strftime('%Y-%m-%d %H:%M')}"
    )

    return df


def find_first_price_at_or_after(df, target_time):
    if df is None or df.empty or target_time is None:
        return None

    pos = df.index.searchsorted(target_time)

    if pos >= len(df.index):
        return None

    price_time = df.index[pos].to_pydatetime()
    close = safe_float(df.iloc[pos]["Close"])

    if close is None:
        return None

    gap_minutes = abs((price_time - target_time).total_seconds()) / 60

    if gap_minutes > MAX_GAP_MINUTES:
        return None

    return {
        "time": price_time,
        "close": close,
        "gap_minutes": gap_minutes,
    }


def build_reaction_for_ticker(df, ticker_meta, news_time):
    ticker = ticker_meta["ticker"]
    label = ticker_meta["label"]
    data_type = ticker_meta["type"]

    t0_target = news_time
    t5_target = news_time + timedelta(minutes=5)

    p0 = find_first_price_at_or_after(df, t0_target)
    p5 = find_first_price_at_or_after(df, t5_target)

    base = {
        "ticker": ticker,
        "label": label,
        "type": data_type,
        "t0_target": t0_target.strftime("%Y-%m-%d %H:%M"),
        "t5_target": t5_target.strftime("%Y-%m-%d %H:%M"),
        "t0_time": None,
        "t5_time": None,
        "t0": None,
        "t5": None,
        "change": None,
        "change_pct": None,
        "change_bp_est": None,
        "available": False,
    }

    if not p0 or not p5:
        return base

    t0 = p0["close"]
    t5 = p5["close"]
    change = t5 - t0

    base["t0_time"] = p0["time"].strftime("%Y-%m-%d %H:%M")
    base["t5_time"] = p5["time"].strftime("%Y-%m-%d %H:%M")
    base["t0"] = round(t0, 6)
    base["t5"] = round(t5, 6)
    base["change"] = round(change, 6)
    base["available"] = True

    if t0 != 0:
        base["change_pct"] = round(change / t0 * 100, 4)

    # Yahoo 的 ^TNX 報價通常是「殖利率 * 10」
    # 例如 43.66 約等於 4.366%，所以 quote 變動 0.04 約等於 0.4bp
    if data_type == "yield":
        base["change_bp_est"] = round(change * 10, 3)

    return base


def add_market_reactions(news_data):
    items = news_data.get("items", [])

    if not items:
        log("No news items. Skip market reaction.")
        return news_data

    price_data = {}

    for key, meta in TICKERS.items():
        try:
            price_data[key] = fetch_price_series(meta["ticker"])
        except Exception as e:
            log(f"Failed to fetch {meta['ticker']}: {e}")
            price_data[key] = pd.DataFrame()

    updated_items = []

    for item in items:
        news_time = parse_news_datetime(item.get("datetime"))

        if not news_time:
            item["market_reaction"] = {}
            updated_items.append(item)
            continue

        reaction = {}

        for key, meta in TICKERS.items():
            df = price_data.get(key, pd.DataFrame())
            reaction[key] = build_reaction_for_ticker(df, meta, news_time)

        item["market_reaction"] = reaction
        updated_items.append(item)

    news_data["items"] = updated_items
    news_data["market_reaction_meta"] = {
        "enabled": True,
        "source": "yfinance",
        "period": PERIOD,
        "interval": INTERVAL,
        "timezone": "Asia/Taipei",
        "tickers": {
            key: {
                "ticker": meta["ticker"],
                "label": meta["label"],
                "type": meta["type"],
            }
            for key, meta in TICKERS.items()
        },
        "method": "For each news timestamp, use the first 1-minute price at or after T0 and T+5 minutes.",
        "max_gap_minutes": MAX_GAP_MINUTES,
        "updated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
    }

    return news_data


def main():
    log("========== Market Reaction Start ==========")

    if not NEWS_INPUT.exists():
        raise FileNotFoundError("data/news.json not found. Please run summarize.py first.")

    news_data = json.loads(NEWS_INPUT.read_text(encoding="utf-8"))

    item_count = len(news_data.get("items", []))
    log(f"Loaded news items: {item_count}")

    news_data = add_market_reactions(news_data)

    NEWS_OUTPUT.write_text(
        json.dumps(news_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log("Saved market reaction to data/news.json")

    items = news_data.get("items", [])
    if items:
        sample = items[0].get("market_reaction", {})
        log("Sample market_reaction from latest item:")
        log(json.dumps(sample, ensure_ascii=False, indent=2))

    log("========== Market Reaction Finished ==========")


if __name__ == "__main__":
    main()
``
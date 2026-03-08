# 1) Imports
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytz
import requests
import streamlit as st
import yfinance as yf


# 2) Global Configuration
# ============================================================
# 全域配置（所有可調參數集中於此，修改指標時只改這裡）
# ============================================================
DATA_PERIODS = {
    "default": "2mo",  # 一般指標（MA20、支撐壓力、20日高低）
    "long_term": "12mo",  # 長期均線（Vegas Tunnel 用，未來啟用）
}

FUTURES_SYMBOLS = ["ES=F", "NQ=F", "VX=F"]
NO_VOLUME_SYMBOLS = {"^VIX", "DX-Y.NYB", "^GSPC", "^IXIC", "^DJI", "ES=F", "NQ=F", "VX=F"}
CACHE_GUARD_SYMBOLS = ["SPY", "QQQ", "^VIX"]
DEFAULT_AI_RESPONSE = "目前無法連線至 AI 獲取解說，請依上方數據自行判斷。"

REGIME_ACTION_MAP = {
    "Risk-Off": {
        "color": "#B71C1C",
        "bg": "#FFEBEE",
        "icon": "🔴",
        "action": "市場極端恐慌，今日全場旁觀，不建議任何新建倉",
        "position_advice": "若有浮盈，優先保護利潤",
    },
    "Liquidity Contraction": {
        "color": "#C62828",
        "bg": "#FFEBEE",
        "icon": "🔴",
        "action": "流動性收縮，有浮盈倉位考慮減倉，等待環境改善",
        "position_advice": "新建倉風險高，耐心等待",
    },
    "High Volatility Risk-Off": {
        "color": "#E65100",
        "bg": "#FFF3E0",
        "icon": "🟠",
        "action": "高波動環境，若有獲利可先保護部分利潤，輕倉觀察",
        "position_advice": "可關注靠近支撐的標的，但倉位控制在平時一半",
    },
    "Risk-On": {
        "color": "#1B5E20",
        "bg": "#E8F5E9",
        "icon": "🟢",
        "action": "市場偏多，可關注觀察股中靠近支撐位的標的順勢輕倉",
        "position_advice": "嚴設停損，不追漲",
    },
    "Range Market": {
        "color": "#37474F",
        "bg": "#ECEFF1",
        "icon": "🟡",
        "action": "震盪整理，等待更明確方向訊號，輕倉觀察為主",
        "position_advice": "不宜重倉，等待突破確認",
    },
}

FUTURES_NAMES = {
    "ES=F": "S&P 期貨",
    "NQ=F": "NASDAQ 期貨",
    "VX=F": "VIX 期貨",
}

SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLI", "XLV", "XLY", "SMH"]
SECTOR_NAMES = {
    "XLK": "科技",
    "XLE": "能源",
    "XLF": "金融",
    "XLI": "工業",
    "XLV": "醫療",
    "XLY": "非必需消費",
    "SMH": "半導體",
}
CORE_MARKET_SYMBOLS = ["SPY", "QQQ", "SMH", "^VIX", "CL=F", "GC=F", "DX-Y.NYB"] + SECTOR_ETFS

UP_COLOR = "#26a69a"
DOWN_COLOR = "#ef5350"
NEUTRAL_COLOR = "#78909c"
WARNING_COLOR = "#FFA726"


# 3) Data Fetch Functions

def fetch_price_data(symbol: str, period: str = DATA_PERIODS["default"]) -> pd.DataFrame | None:
    """
    標準化 yfinance 抓取。
    指數類標的（VIX、DXY 等）不進行 Volume > 0 過濾。
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d")
        if df is None or df.empty:
            return None
        df = df.dropna(subset=["Close"])
        if symbol not in NO_VOLUME_SYMBOLS and "Volume" in df.columns:
            df = df[df["Volume"] > 0]
        if len(df) < 2:
            return None
        return df
    except Exception:
        return None


def fetch_fred_us10y_details(fred_api_key: str) -> dict[str, float | str | None]:
    """抓取 FRED DGS10，limit=10 並跳過 '.', '', None。"""
    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=DGS10&sort_order=desc&limit=10&api_key={fred_api_key}&file_type=json"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        observations = resp.json().get("observations", [])

        valid_vals: list[float] = []
        for obs in observations:
            val = obs.get("value", ".")
            if val not in [".", "", None]:
                valid_vals.append(float(val))
            if len(valid_vals) >= 2:
                break

        if not valid_vals:
            return {"value": "無法取得", "delta": None}

        current = valid_vals[0]
        prev = valid_vals[1] if len(valid_vals) > 1 else None
        delta = (current - prev) if isinstance(prev, float) else None
        return {"value": current, "delta": delta}
    except Exception:
        return {"value": "無法取得", "delta": None}


def fetch_binance_btc() -> dict[str, float | str | None]:
    """抓取 BTC 即時價格與 24H 漲跌幅。"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "price": float(data.get("lastPrice")),
            "pct": float(data.get("priceChangePercent")),
        }
    except Exception:
        return {"price": "無法取得", "pct": "無法取得"}

def fetch_premarket_futures() -> dict[str, dict[str, Any] | None]:
    """抓取盤前期貨今日累積漲跌幅（以今日期貨開盤第一筆為基準）。"""
    results: dict[str, dict[str, Any] | None] = {}
    for symbol in FUTURES_SYMBOLS:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval="5m")
            df = df.dropna(subset=["Close"])
            if len(df) < 2:
                results[symbol] = None
                continue
            first_price = df["Close"].iloc[0]
            last_price = df["Close"].iloc[-1]
            if first_price == 0 or pd.isna(first_price):
                results[symbol] = None
                continue
            pct = (last_price - first_price) / first_price * 100
            results[symbol] = {
                "price": round(float(last_price), 2),
                "pct": round(float(pct), 2),
                "time": df.index[-1].strftime("%H:%M ET") if hasattr(df.index[-1], "strftime") else "N/A",
            }
        except Exception:
            results[symbol] = None
    return results


# 4) Indicator Calculations

def calc_pct_change(df: pd.DataFrame) -> float | None:
    """取最後兩個有效收盤日計算漲跌幅，含除以零保護。"""
    closes = df["Close"].tail(2).values
    if len(closes) < 2:
        return None
    prev_close = closes[-2]
    if prev_close == 0 or pd.isna(prev_close):
        return None
    return float((closes[-1] - prev_close) / prev_close * 100)


def calc_watchlist_stats(df: pd.DataFrame, spy_pct: float | None = None) -> dict[str, Any] | None:
    """計算觀察股均線、支撐壓力統計，含 ATR(14) 與 RS vs SPY，失敗回傳 None。"""
    try:
        latest_close = float(df["Close"].iloc[-1])
        day_pct = calc_pct_change(df)

        ma20 = float(df["Close"].rolling(20).mean().iloc[-1])
        ma20_pct = (latest_close - ma20) / ma20 * 100 if ma20 != 0 and not np.isnan(ma20) else None

        support = float(df["Low"].rolling(20).min().iloc[-1])
        dist_support_pct = (latest_close - support) / support * 100 if support != 0 and not np.isnan(support) else None

        resistance = float(df["High"].rolling(20).max().iloc[-1])
        dist_resistance_pct = (
            (latest_close - resistance) / resistance * 100
            if resistance != 0 and not np.isnan(resistance)
            else None
        )

        if ma20_pct is not None:
            if ma20_pct > 3:
                status = "📈 偏強"
            elif ma20_pct < -3:
                status = "📉 偏弱"
            else:
                status = "➡️ 中性"
        else:
            status = "N/A"

        try:
            high = df["High"].tail(15)
            low = df["Low"].tail(15)
            close_prev = df["Close"].tail(15).shift(1)
            tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
            atr = round(float(tr.tail(14).mean()), 2)
        except Exception:
            atr = None

        stock_pct = (
            (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100
            if len(df) >= 2 and df["Close"].iloc[-2] != 0
            else None
        )
        if isinstance(stock_pct, float) and isinstance(spy_pct, float):
            rs_vs_spy = round(stock_pct - spy_pct, 2)
        else:
            rs_vs_spy = None

        return {
            "現價": round(latest_close, 2),
            "日漲跌(%)": round(day_pct, 2) if isinstance(day_pct, (int, float)) else "N/A",
            "MA20": round(ma20, 2) if pd.notna(ma20) else "N/A",
            "距MA20(%)": round(ma20_pct, 2) if ma20_pct is not None else "N/A",
            "支撐位": round(support, 2) if pd.notna(support) else "N/A",
            "距支撐(%)": round(dist_support_pct, 2) if dist_support_pct is not None else "N/A",
            "壓力位": round(resistance, 2) if pd.notna(resistance) else "N/A",
            "距壓力(%)": round(dist_resistance_pct, 2) if dist_resistance_pct is not None else "N/A",
            "ATR(14)": round(atr, 2) if atr is not None else "N/A",
            "RS vs SPY": f"{rs_vs_spy:+.2f}%" if rs_vs_spy is not None else "N/A",
            "狀態": status,
        }
    except Exception:
        return None


# 5) Market Regime Engine

def determine_market_regime(
    vix_pct: float | None,
    vix_val: float | None,
    qqq_pct: float | None,
    spy_pct: float | None,
    us10y_val: float | str,
    oil_pct: float | None,
) -> str:
    """固定規則判定 Market Regime。"""

    def safe(val: Any, default: float = 0.0) -> float:
        return float(val) if isinstance(val, (int, float)) else default

    v_pct = safe(vix_pct)
    v_val = safe(vix_val)
    q_pct = safe(qqq_pct)
    s_pct = safe(spy_pct)
    o_pct = safe(oil_pct)
    us10y = safe(us10y_val)

    if (v_pct > 15 and q_pct < -2) or (v_val > 30):
        return "Risk-Off"
    if us10y > 4.0 and v_val > 20 and o_pct > 0:
        return "Liquidity Contraction"
    if v_val > 25 and q_pct < 0:
        return "High Volatility Risk-Off"
    if s_pct > 0 and q_pct > 0 and v_pct < 0:
        return "Risk-On"
    return "Range Market"


def determine_risk_type(
    vix_pct: float | None,
    vix_val: float | None,
    us10y_rising: bool,
    oil_rising: bool,
    spy_above_ma20: bool,
) -> str:
    v_pct = vix_pct if isinstance(vix_pct, (int, float)) else 0.0
    v_val = vix_val if isinstance(vix_val, (int, float)) else 0.0

    if v_val > 25 and us10y_rising and oil_rising:
        return "⚠️ 結構性壓力升高"
    if v_pct > 20:
        return "🌊 事件型波動"
    if v_pct > 0 and not us10y_rising and spy_above_ma20:
        return "💧 情緒性洗盤"
    return "🟡 中性觀察"


def generate_structural_explanation(
    risk_type: str,
    vix_val: float | None,
    us10y_val: float | str,
    oil_pct: float | None,
    spy_pct: float | None,
) -> str:
    """根據觸發判定結果，生成中文解說段落。"""
    try:
        vix_txt = f"{vix_val:.1f}" if isinstance(vix_val, (int, float)) else "N/A"
        us10y_txt = f"{us10y_val:.2f}" if isinstance(us10y_val, (int, float)) else "N/A"
        oil_txt = f"{oil_pct:.1f}" if isinstance(oil_pct, (int, float)) else "N/A"

        explanations = {
            "⚠️ 結構性壓力升高": (
                f"VIX 升至 {vix_txt}，同時美債殖利率維持高位（{us10y_txt}%），"
                f"原油亦走升 {oil_txt}%。三項壓力指標同步走升，"
                "代表市場不只是技術性回檔，而是在重新定價通膨與流動性風險。建議今日以觀察為主，不追高。"
            ),
            "🌊 事件型波動": (
                "VIX 單日暴漲，顯示市場發生突發性事件驅動的急速拋售。"
                "此類波動通常較短暫，但方向不明，建議靜待市場消化消息後再行動。"
            ),
            "💧 情緒性洗盤": (
                "VIX 雖有上升，但美債殖利率未同步走升，SPY 仍維持在均線上方。"
                "這是典型的情緒性洗盤特徵，基本面未受威脅，跌幅可能有限。可適度關注買點。"
            ),
            "🟡 中性觀察": "各項壓力指標未出現明顯異常，市場處於相對穩定狀態，維持正常倉位管理即可。",
        }
        _ = spy_pct
        return explanations.get(risk_type, "無法生成結構解說，請參考上方數據。")
    except Exception:
        return "無法生成結構解說，請參考上方數據。"


# 6) Narrative Engine

def generate_narrative(
    regime: str,
    best_sector: str,
    worst_sector: str,
    us10y_val: float | str,
    oil_pct: float | None,
    vix_val: float | None,
) -> str:
    """規則模板 Narrative 引擎。"""
    regime_text = {
        "Risk-Off": "市場處於恐慌性拋售狀態，多數風險資產同步下跌",
        "Liquidity Contraction": "債市、油市與波動率三重走升，市場進入流動性收縮環境",
        "High Volatility Risk-Off": "市場波動率偏高，風險資產面臨賣壓，但尚未達到極端恐慌",
        "Risk-On": "市場情緒轉樂觀，風險資產普遍走強",
        "Range Market": "市場方向尚不明確，各項指標呈震盪格局，觀望為宜",
    }.get(regime, "市場狀態不明")

    rate_text = f"美債殖利率報 {us10y_val:.2f}%，" if isinstance(us10y_val, (int, float)) else ""
    oil_display = f"{abs(oil_pct):.1f}%" if isinstance(oil_pct, (int, float)) else "N/A"
    oil_dir = "走升" if isinstance(oil_pct, (int, float)) and oil_pct > 0 else "走低"
    oil_text = f"原油{oil_dir} {oil_display}，" if oil_pct is not None else ""
    _ = vix_val

    action_advice = "謹慎觀望、輕倉為主" if regime in ["Risk-Off", "Liquidity Contraction"] else "順勢操作、嚴設停損"

    return (
        f"{regime_text}。{rate_text}{oil_text}"
        f"{best_sector} 板塊表現相對強勢，{worst_sector} 板塊承壓。"
        f"今日操作建議以{action_advice}為原則。"
    )


def fetch_news_context(gemini_api_key: str) -> str:
    """使用 Gemini Search Grounding 搜尋今日財經新聞摘要。"""
    if not gemini_api_key:
        return ""
    try:
        import google.generativeai as genai

        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")
        news_prompt = (
            "請用繁體中文，用50字以內，列出最近1-2則"
            "最可能直接影響美國科技股或整體大盤的重大財經新聞事件。"
            "只列事件本身，不要解釋，不要加標點以外的格式。"
        )
        response = model.generate_content(news_prompt, tools=[{"google_search": {}}])
        news_text = response.text.strip() if getattr(response, "text", None) else ""
        return news_text[:200]
    except Exception as e:
        try:
            st.sidebar.caption(f"⚠️ 新聞搜尋不可用：{type(e).__name__}")
        except Exception:
            pass
        return ""


def build_ai_prompt(data: dict[str, Any]) -> str:
    """動態組裝規格定義的 User Prompt。"""
    return (
        "請基於以下昨日美股收盤數據，用繁體中文撰寫：\n"
        "1. 一段「盤前白話解說」（100字以內，解釋今天市場在演什麼、為什麼）\n"
        "2. 一句「今日操作策略」（20字以內，具備防呆性質）\n"
        "3. 一段「事件脈絡」（50字以內，說明近期事件影響）\n\n"
        "數據如下：\n"
        f"- SPY 漲跌：{data.get('spy_pct')}%\n"
        f"- QQQ 漲跌：{data.get('qqq_pct')}%\n"
        f"- VIX 數值：{data.get('vix_val')}（日漲跌 {data.get('vix_pct')}%）\n"
        f"- 10年期美債殖利率：{data.get('us10y_val')}%\n"
        f"- WTI 原油漲跌：{data.get('oil_pct')}%\n"
        f"- 系統判定 Market Regime：{data.get('market_regime')}\n"
        f"- 情緒洗盤 vs 結構風險判定：{data.get('risk_type')}\n"
        f"- 最強板塊：{data.get('best_sector')}（{data.get('best_pct')}%）\n"
        f"- 最弱板塊：{data.get('worst_sector')}（{data.get('worst_pct')}%）\n\n"
        "輸出格式（請嚴格遵守，不要加任何 Markdown 標題）：\n"
        "[盤前解說]：...（100字以內，解釋今天市場在演什麼、為什麼）\n"
        "[今日策略]：...（20字以內，具備防呆性質）\n"
        "[事件脈絡]：...（50字以內，說明近期事件對哪個板塊有影響，若無新聞資訊則填「無特殊事件，以數據為主要依據」）"
    )


def call_ai_analysis(
    gemini_api_key: str,
    openai_api_key: str,
    prompt: str,
    news_context: str,
) -> str:
    """V1.3 三層降級 AI 分析。"""
    if openai_api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=openai_api_key)
            full_prompt = prompt
            if news_context:
                full_prompt += f"\n\n近期重大財經事件（由 Google 搜尋取得）：\n{news_context}"



            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一位冷靜、重風險控管的美股波段交易員，"
                            "擅長用最簡單的語言解釋市場給新手聽。"
                            "不誇大、不預測未來、強調風險控管。"
                        ),
                    },
                    {"role": "user", "content": full_prompt},
                ],
                max_tokens=300,
                temperature=0.4,
            )
            result = response.choices[0].message.content.strip()
            if result:
                return result
        except Exception:
            pass

    if gemini_api_key:
        try:
            import google.generativeai as genai

            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel("gemini-3-flash-preview")
            full_prompt = prompt
            if news_context:
                full_prompt += f"\n\n近期重大財經事件：\n{news_context}"



            response = model.generate_content(full_prompt)
            result = response.text.strip() if getattr(response, "text", None) else ""
            if result:
                return result
        except Exception:
            pass

    return DEFAULT_AI_RESPONSE


# 7) Session Cache Layer

def _fetch_all_data(
    watchlist_symbols: list[str],
    fred_api_key: str,
    gemini_api_key: str,
    openai_api_key: str,
) -> dict[str, Any]:
    """執行所有外部抓取與計算；僅回傳統計結果字典（不含 DataFrame）。"""
    market_data: dict[str, Any] = {
        "symbols": {},
        "sector_changes": {},
        "watchlist": [],
        "raw_data": [],
        "ai_response": DEFAULT_AI_RESPONSE,
        "warnings": [],
    }

    all_symbols = CORE_MARKET_SYMBOLS + watchlist_symbols
    price_data: dict[str, pd.DataFrame] = {}

    pct_changes: dict[str, float | None] = {}
    for symbol in all_symbols:
        try:
            df = fetch_price_data(symbol)
            if df is not None:
                price_data[symbol] = df
                pct_changes[symbol] = calc_pct_change(df)
            else:
                pct_changes[symbol] = None
                market_data["warnings"].append(f"⚠️ {symbol} 價格資料抓取失敗或為空。")
        except Exception:
            pct_changes[symbol] = None
            market_data["warnings"].append(f"⚠️ {symbol} 價格資料抓取發生例外。")

    for symbol in CORE_MARKET_SYMBOLS:
        try:
            df = price_data.get(symbol)
            close_val = float(df["Close"].iloc[-1]) if df is not None else None
            sym_payload = {
                "price": round(close_val, 2) if isinstance(close_val, (int, float)) else None,
                "pct": pct_changes.get(symbol),
            }
            market_data["symbols"][symbol] = sym_payload
            market_data[symbol] = sym_payload if close_val is not None else None
        except Exception:
            market_data["symbols"][symbol] = {"price": None, "pct": None}
            market_data[symbol] = None

    try:
        fred_details = fetch_fred_us10y_details(fred_api_key)
    except Exception:
        fred_details = {"value": "無法取得", "delta": None}
        market_data["warnings"].append("⚠️ FRED（10年期美債殖利率）資料抓取發生例外。")
    if not isinstance(fred_details.get("value"), (int, float)):
        market_data["warnings"].append("⚠️ FRED（10年期美債殖利率）資料不可用。")
    market_data["us10y"] = fred_details

    try:
        btc_data = fetch_binance_btc()
    except Exception:
        btc_data = {"price": "無法取得", "pct": "無法取得"}
        market_data["warnings"].append("⚠️ Binance（BTC）資料抓取發生例外。")
    if not isinstance(btc_data.get("price"), (int, float)):
        market_data["warnings"].append("⚠️ Binance（BTC）資料不可用。")
    market_data["btc"] = btc_data

    spy_df = price_data.get("SPY")
    qqq_df = price_data.get("QQQ")
    vix_df = price_data.get("^VIX")

    spy_pct = pct_changes.get("SPY")
    qqq_pct = pct_changes.get("QQQ")
    vix_pct = pct_changes.get("^VIX")
    oil_pct = pct_changes.get("CL=F")

    vix_val = None
    if vix_df is not None:
        try:
            vix_val = float(vix_df["Close"].iloc[-1])
        except Exception:
            vix_val = None

    us10y_val = fred_details.get("value", "無法取得")

    regime = determine_market_regime(vix_pct, vix_val, qqq_pct, spy_pct, us10y_val, oil_pct)

    us10y_delta = fred_details.get("delta")
    us10y_rising = bool(isinstance(us10y_delta, (int, float)) and us10y_delta > 0)
    oil_rising = bool(isinstance(oil_pct, (int, float)) and oil_pct > 0)

    spy_above_ma20 = False
    try:
        if spy_df is not None:
            spy_ma20 = float(spy_df["Close"].rolling(20).mean().iloc[-1])
            spy_close = float(spy_df["Close"].iloc[-1])
            if spy_ma20 != 0 and not np.isnan(spy_ma20):
                spy_above_ma20 = spy_close > spy_ma20
    except Exception:
        spy_above_ma20 = False

    risk_type = determine_risk_type(vix_pct, vix_val, us10y_rising, oil_rising, spy_above_ma20)

    for sector in SECTOR_ETFS:
        market_data["sector_changes"][sector] = pct_changes.get(sector)

    sortable = [
        (sector, pct)
        for sector, pct in market_data["sector_changes"].items()
        if isinstance(pct, (int, float))
    ]
    sortable = sorted(sortable, key=lambda x: x[1], reverse=True)

    best_sector = SECTOR_NAMES.get(sortable[0][0], "N/A") if sortable else "N/A"
    worst_sector = SECTOR_NAMES.get(sortable[-1][0], "N/A") if sortable else "N/A"
    best_pct = round(sortable[0][1], 2) if sortable else "N/A"
    worst_pct = round(sortable[-1][1], 2) if sortable else "N/A"

    try:
        narrative = generate_narrative(regime, best_sector, worst_sector, us10y_val, oil_pct, vix_val)
    except Exception:
        narrative = "市場敘事生成失敗，請參考上方指標數據。"

    for symbol in watchlist_symbols:
        row = {
            "股票代號": symbol,
            "現價": "N/A",
            "日漲跌(%)": "N/A",
            "MA20": "N/A",
            "距MA20(%)": "N/A",
            "支撐位": "N/A",
            "距支撐(%)": "N/A",
            "壓力位": "N/A",
            "距壓力(%)": "N/A",
            "ATR(14)": "N/A",
            "RS vs SPY": "N/A",
            "狀態": "N/A",
        }
        try:
            df = price_data.get(symbol)
            if df is not None:
                stats = calc_watchlist_stats(df, spy_pct=spy_pct)
                if stats is not None:
                    row.update(stats)
        except Exception:
            pass
        market_data["watchlist"].append(row)

    market_data["raw_data"] = [
        {"symbol": sym, "price": data.get("price"), "pct": data.get("pct")}
        for sym, data in market_data["symbols"].items()
    ]

    market_data.update(
        {
            "spy_pct": spy_pct,
            "qqq_pct": qqq_pct,
            "vix_pct": vix_pct,
            "vix_val": round(vix_val, 2) if isinstance(vix_val, (int, float)) else None,
            "oil_pct": oil_pct,
            "us10y_val": us10y_val,
            "market_regime": regime,
            "risk_type": risk_type,
            "best_sector": best_sector,
            "worst_sector": worst_sector,
            "best_pct": best_pct,
            "worst_pct": worst_pct,
            "narrative": narrative,
            "us10y_rising": us10y_rising,
            "oil_rising": oil_rising,
            "spy_above_ma20": spy_above_ma20,
            "us10y_delta": us10y_delta,
        }
    )

    structural_explanation = generate_structural_explanation(
        risk_type, vix_val, us10y_val, oil_pct, spy_pct
    )
    market_data["structural_explanation"] = structural_explanation

    try:
        futures_data = fetch_premarket_futures()
    except Exception:
        futures_data = {}
    market_data["futures_data"] = futures_data

    if gemini_api_key or openai_api_key:
        try:
            news_context = fetch_news_context(gemini_api_key)
        except Exception:
            news_context = ""

        try:
            ai_response = call_ai_analysis(
                gemini_api_key=gemini_api_key,
                openai_api_key=openai_api_key,
                prompt=build_ai_prompt(market_data),
                news_context=news_context,
            )
            market_data["ai_response"] = ai_response if ai_response and ai_response.strip() else DEFAULT_AI_RESPONSE
        except Exception:
            market_data["ai_response"] = DEFAULT_AI_RESPONSE
    else:
        market_data["ai_response"] = ""

    return market_data


def _is_valid_cache_symbol_payload(data: dict[str, Any], symbol: str) -> bool:
    payload = data.get(symbol)
    if not isinstance(payload, dict):
        return False
    return isinstance(payload.get("price"), (int, float))


def _has_valid_cache_guard_data(data: dict[str, Any]) -> bool:
    return all(_is_valid_cache_symbol_payload(data, sym) for sym in CACHE_GUARD_SYMBOLS)




# 8) Streamlit UI Rendering

def _fmt_metric_value(value: float | str | None, prefix: str = "") -> str:
    if isinstance(value, (int, float)):
        return f"{prefix}{value:,.2f}"
    return "N/A"


def _fmt_delta(value: float | str | None) -> str:
    if isinstance(value, (int, float)):
        return f"{value:+.2f}%"
    return "N/A"


def _regime_badge(regime: str) -> None:
    """V1.3：全幅彩色 Regime 橫幅。"""
    config_map = {
        "Risk-Off": ("🔴", "#B71C1C", "#FFCDD2"),
        "Liquidity Contraction": ("🔴", "#C62828", "#FFEBEE"),
        "High Volatility Risk-Off": ("🟠", "#E65100", "#FFF3E0"),
        "Risk-On": ("🟢", "#1B5E20", "#E8F5E9"),
        "Range Market": ("🟡", "#37474F", "#ECEFF1"),
    }
    icon, color, bg = config_map.get(regime, ("⚪", "#333", "#F5F5F5"))
    st.markdown(
        f"""
    <div style="
        background-color: {bg};
        border: 2px solid {color};
        border-radius: 12px;
        padding: 20px 28px;
        text-align: center;
        margin-bottom: 20px;
    ">
        <div style="font-size: 48px; margin-bottom: 8px;">{icon}</div>
        <div style="font-size: 26px; font-weight: 900; color: {color}; letter-spacing: 1px;">
            {regime}
        </div>
        <div style="font-size: 13px; color: #666; margin-top: 6px;">
            Market Regime — 今日市場環境判定
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def _parse_ai_response(raw: str) -> dict[str, str]:
    """解析 AI 三段格式輸出，失敗時保底。"""
    result = {"盤前解說": "", "今日策略": "", "事件脈絡": ""}
    try:
        import re

        matches = re.findall(r"\[([^\]]+)\]：(.+?)(?=\[|$)", raw or "", re.DOTALL)
        for key, value in matches:
            key = key.strip()
            if key in result:
                result[key] = value.strip()
        if not any(result.values()):
            result["盤前解說"] = (raw or "").strip()
    except Exception:
        result["盤前解說"] = (raw or "").strip()
    return result


def _clean_watchlist_df(raw_data: list[dict[str, Any]]) -> pd.DataFrame:
    """將 N/A 字串轉為 NaN，確保 dataframe 格式化正常。"""
    df = pd.DataFrame(raw_data)
    numeric_cols = ["現價", "MA20", "距MA20(%)", "支撐位", "距支撐(%)", "壓力位", "距壓力(%)", "日漲跌(%)", "ATR(14)"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _render_action_banner(data: dict[str, Any]) -> None:
    """根據 Market Regime 和觀察股狀態渲染頂部行動建議框。"""
    regime = data.get("market_regime", "Range Market")
    config = REGIME_ACTION_MAP.get(regime, REGIME_ACTION_MAP["Range Market"])

    st.markdown(
        f"""
    <div style="
        background-color: {config['bg']};
        border-left: 6px solid {config['color']};
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 16px;
    ">
        <h3 style="color: {config['color']}; margin: 0 0 8px 0;">
            {config['icon']} 今日大環境：{regime}
        </h3>
        <p style="margin: 0 0 4px 0; font-size: 15px;">
            ▶ <strong>{config['action']}</strong>
        </p>
        <p style="margin: 0; color: #555; font-size: 13px;">
            💼 持倉提醒：{config['position_advice']}
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    watchlist_stats = {row.get("股票代號"): row for row in data.get("watchlist", [])}
    if watchlist_stats:
        worth_watching = []
        need_caution = []
        for symbol, stats in watchlist_stats.items():
            if not isinstance(stats, dict):
                continue
            ma20_pct = stats.get("距MA20(%)")
            dist_support = stats.get("距支撐(%)")
            status = stats.get("狀態", "")
            if not isinstance(ma20_pct, (int, float)):
                continue
            if "偏強" in status and isinstance(dist_support, (int, float)) and dist_support < 8:
                worth_watching.append(f"**{symbol}**（偏強，距支撐 {dist_support:.1f}%）")
            elif "偏弱" in status:
                need_caution.append(f"**{symbol}**（偏弱，距MA20 {ma20_pct:.1f}%）")

        col1, col2 = st.columns(2)
        with col1:
            if regime in ["Risk-Off", "Liquidity Contraction"]:
                st.markdown("📍 **可關注**：⚠️ 高風險環境，所有標的暫停關注")
            elif worth_watching:
                st.markdown("📍 **可關注**：" + "、".join(worth_watching[:3]))
            else:
                st.markdown("📍 **可關注**：目前無明顯機會標的")
        with col2:
            if need_caution:
                st.markdown("⚠️ **需警覺**：" + "、".join(need_caution[:3]))
            else:
                st.markdown("⚠️ **需警覺**：觀察股整體穩定")

        st.divider()


def _render_all_tabs(data: dict[str, Any]) -> None:
    _render_action_banner(data)

    tab1, tab2, tab3, tab4 = st.tabs([
        "🌡️ 市場戰情總覽",
        "🔍 結構分析",
        "🔄 資金輪動雷達",
        "🎯 觀察股雷達",
    ])

    with tab1:
        _regime_badge(data.get('market_regime', 'Range Market'))
        futures = data.get('futures_data', {})
        if any(futures.get(s) for s in FUTURES_SYMBOLS):
            st.caption(
                "⏰ 盤前期貨動態（今日期貨開盤以來累積，非昨收基準）｜數字小代表今日盤前平靜，不代表數據異常"
            )
            fut_cols = st.columns(len(FUTURES_SYMBOLS))
            for i, symbol in enumerate(FUTURES_SYMBOLS):
                f = futures.get(symbol)
                name = FUTURES_NAMES[symbol]
                with fut_cols[i]:
                    if f:
                        st.metric(
                            label=f"{name}（{symbol}）",
                            value=f"${f['price']:,.1f}" if symbol != "VX=F" else f"{f['price']:.1f}",
                            delta=f"{f['pct']:+.2f}%",
                        )
                    else:
                        st.metric(label=name, value="N/A", delta=None)
            st.divider()

        warnings = data.get("warnings", [])
        if warnings:
            st.warning("⚠️ 本次資料抓取存在異常，以下為診斷訊息：")
            for msg in warnings:
                st.caption(msg)

        c1, c2, c3, c4 = st.columns(4)
        core = data.get("symbols", {})
        with c1:
            st.metric("SPY", _fmt_metric_value(core.get("SPY", {}).get("price"), "$"), _fmt_delta(core.get("SPY", {}).get("pct")))
        with c2:
            st.metric("QQQ", _fmt_metric_value(core.get("QQQ", {}).get("price"), "$"), _fmt_delta(core.get("QQQ", {}).get("pct")))
        with c3:
            st.metric("SMH", _fmt_metric_value(core.get("SMH", {}).get("price"), "$"), _fmt_delta(core.get("SMH", {}).get("pct")))
        with c4:
            st.metric(
                "VIX（VIX ↑ = 市場壓力增加）",
                _fmt_metric_value(core.get("^VIX", {}).get("price")),
                _fmt_delta(core.get("^VIX", {}).get("pct")),
            )

        c5, c6, c7, c8 = st.columns(4)
        with c5:
            st.metric("WTI 原油", _fmt_metric_value(core.get("CL=F", {}).get("price"), "$"), _fmt_delta(core.get("CL=F", {}).get("pct")))
        with c6:
            st.metric("黃金", _fmt_metric_value(core.get("GC=F", {}).get("price"), "$"), _fmt_delta(core.get("GC=F", {}).get("pct")))
        with c7:
            st.metric("DXY", _fmt_metric_value(core.get("DX-Y.NYB", {}).get("price")), _fmt_delta(core.get("DX-Y.NYB", {}).get("pct")))
        with c8:
            btc = data.get("btc", {})
            st.metric("BTC", _fmt_metric_value(btc.get("price"), "$"), _fmt_delta(btc.get("pct")))

        us10y = data.get("us10y", {})
        st.metric("10年期美債殖利率", _fmt_metric_value(us10y.get("value"), ""), _fmt_delta(us10y.get("delta")))

        st.info(f"🧭 Market Narrative：{data.get('narrative', 'N/A')}")

        ai_response = data.get("ai_response", "")
        if ai_response:
            st.info(f"🤖 AI 盤前白話解說\n\n{ai_response}")
        else:
            st.warning("請輸入 API Key 以啟用 AI 解說功能")

    with tab2:
        risk_type = data.get("risk_type", "🟡 中性觀察")
        if risk_type == "⚠️ 結構性壓力升高":
            st.error(risk_type)
        elif risk_type in {"🌊 事件型波動", "🟡 中性觀察"}:
            st.warning(risk_type)
        else:
            st.success(risk_type)

        st.write(data.get("structural_explanation", "無法生成結構解說，請參考上方數據。"))
        st.divider()

        us10y_delta = data.get("us10y_delta")
        condition_rows = [
            {
                "判斷條件": "VIX > 25",
                "數值": data.get("vix_val") if data.get("vix_val") is not None else "N/A",
                "是否觸發": "✅" if isinstance(data.get("vix_val"), (int, float)) and data.get("vix_val") > 25 else "❌",
            },
            {
                "判斷條件": "US10Y 上升",
                "數值": f"{us10y_delta:+.2f}%" if isinstance(us10y_delta, (int, float)) else "N/A",
                "是否觸發": "✅" if data.get("us10y_rising") else "❌",
            },
            {
                "判斷條件": "原油上升",
                "數值": _fmt_delta(data.get("oil_pct")),
                "是否觸發": "✅" if data.get("oil_rising") else "❌",
            },
        ]
        st.table(pd.DataFrame(condition_rows))

    with tab3:
        sector_changes = data.get("sector_changes", {})
        chart_data = []
        for sec in SECTOR_ETFS:
            pct = sector_changes.get(sec)
            if isinstance(pct, (int, float)):
                chart_data.append((SECTOR_NAMES.get(sec, sec), pct))
        chart_data = sorted(chart_data, key=lambda x: x[1], reverse=True)

        if chart_data:
            labels = [x[0] for x in chart_data]
            vals = [x[1] for x in chart_data]
            colors = [UP_COLOR if v >= 0 else DOWN_COLOR for v in vals]

            fig = go.Figure(
                go.Bar(
                    x=vals,
                    y=labels,
                    orientation="h",
                    marker_color=colors,
                    text=[f"{v:+.2f}%" for v in vals],
                    textposition="auto",
                )
            )
            fig.update_layout(
                template="plotly_dark",
                title="七大板塊 ETF 單日漲跌幅",
                xaxis_title="漲跌幅 (%)",
                yaxis_title="板塊",
                height=420,
            )
            fig.add_annotation(
                x=vals[0],
                y=labels[0],
                text=f"最強：{labels[0]}",
                showarrow=False,
                yshift=20,
                font=dict(color=UP_COLOR),
            )
            fig.add_annotation(
                x=vals[-1],
                y=labels[-1],
                text=f"最弱：{labels[-1]}",
                showarrow=False,
                yshift=-20,
                font=dict(color=DOWN_COLOR),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("板塊資料不足，無法繪製資金輪動圖。")

    with tab4:
        regime = data.get("market_regime", "Range Market")
        if regime in ["Risk-Off", "Liquidity Contraction"]:
            st.error(
                f"⚠️ **{regime} 環境警示**：大環境風險偏高，觀察股中所有標的暫停追高。有浮盈倉位請提高警覺，等待環境改善再行動。"
            )
        elif regime == "High Volatility Risk-Off":
            st.warning("🟠 **高波動環境**：個股操作建議輕倉，等待大環境明確後再加碼。")
        elif regime == "Risk-On":
            st.success("🟢 **Risk-On 環境**：可關注觀察股中偏強、靠近支撐位的標的，嚴設停損。")

        watchlist_rows = data.get("watchlist", [])
        watch_df = _clean_watchlist_df(watchlist_rows)
        if not watch_df.empty:
            def _style_status(val: Any) -> str:
                if val == "📈 偏強":
                    return f"color: {UP_COLOR}; font-weight: bold;"
                if val == "📉 偏弱":
                    return f"color: {DOWN_COLOR}; font-weight: bold;"
                if val == "➡️ 中性":
                    return f"color: {NEUTRAL_COLOR}; font-weight: bold;"
                return ""

            styled = watch_df.style.map(_style_status, subset=["狀態"]) if "狀態" in watch_df.columns else watch_df
            st.dataframe(
                styled,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "現價": st.column_config.NumberColumn("現價", format="$%.2f"),
                    "MA20": st.column_config.NumberColumn("MA20", format="$%.2f"),
                    "距MA20(%)": st.column_config.NumberColumn("距MA20(%)", format="%.2f%%"),
                    "支撐位": st.column_config.NumberColumn("支撐位", format="$%.2f"),
                    "距支撐(%)": st.column_config.NumberColumn("距支撐(%)", format="%.2f%%"),
                    "壓力位": st.column_config.NumberColumn("壓力位", format="$%.2f"),
                    "距壓力(%)": st.column_config.NumberColumn("距壓力(%)", format="%.2f%%"),
                    "日漲跌(%)": st.column_config.NumberColumn("日漲跌(%)", format="%.2f%%"),
                    "ATR(14)": st.column_config.NumberColumn(
                        "ATR(14)", format="$%.2f", help="14日平均波幅，代表該股正常一日可能的價格波動範圍"
                    ),
                    "RS vs SPY": st.column_config.TextColumn(
                        "RS vs SPY", help="個股單日漲跌幅 − SPY 單日漲跌幅，正值表示跑贏大盤"
                    ),
                },
            )
        else:
            st.info("尚無觀察股資料。")

        with st.expander("📄 查看原始數據（偵錯用）"):
            st.dataframe(pd.DataFrame(data.get("raw_data", [])), use_container_width=True)

        with st.expander("🩺 查看資料來源診斷（偵錯用）"):
            warnings = data.get("warnings", [])
            if warnings:
                st.table(pd.DataFrame({"warning": warnings}))
            else:
                st.caption("本次抓取無額外警示。")


# 9) Main Application Entry

def main() -> None:
    st.set_page_config(page_title="專屬盤前戰情室 V1.3", layout="wide")

    st.header("🚦 專屬盤前戰情室 V1.3", divider="rainbow")

    st.sidebar.header("📊 War Room Setup", divider="rainbow")
    gemini_api_key = st.sidebar.text_input(
        "🔍 Gemini API Key（新聞搜尋主力）",
        type="password",
        help="用於 Google Search Grounding 自動搜尋今日財經新聞",
    )
    openai_api_key = st.sidebar.text_input(
        "🤖 OpenAI API Key（分析備援）",
        type="password",
        help="用於白話解說主力分析，Gemini 失敗時自動接手",
    )
    fred_api_key = st.sidebar.text_input("請輸入 FRED API Key", type="password")
    st.sidebar.caption("💡 兩個 Key 均非必填：僅 Gemini=新聞+分析；僅 OpenAI=純數據分析；都不填=僅規則引擎")
    st.sidebar.divider()

    default_watchlist = "NVDA\nTSM\nAMD\nGOOG\nPLTR"
    watchlist_text = st.sidebar.text_area(
        "觀察股清單",
        value=default_watchlist,
        help="每行輸入一個股票代號",
    )
    st.sidebar.divider()

    if "last_updated" in st.session_state:
        st.sidebar.caption(f"🕐 快取更新：{st.session_state['last_updated']}")
        st.sidebar.caption("（核心指標完整時自動保存）")

    st.sidebar.markdown(
        """
---
### 📢 免責聲明
本系統僅為個人盤前資訊整理工具。
AI 解說**不構成任何投資建議**。
所有交易決策請自行判斷，嚴格控管風險。
"""
    )

    watchlist_symbols = [line.strip().upper() for line in watchlist_text.splitlines() if line.strip()]

    if "market_data" in st.session_state:
        st.info(
            f"📌 顯示最後一次完整戰報（更新於 {st.session_state['last_updated']}）。"
            "點擊按鈕可刷新數據。"
        )
        _render_all_tabs(st.session_state["market_data"])
    else:
        st.markdown(
            "### 👋 歡迎使用盤前戰情室\n"
            "請在左側輸入 API Key，再點擊「🔄 獲取最新盤前戰報」開始分析。"
        )

    if st.button("🔄 獲取最新盤前戰報", use_container_width=True):
        if not fred_api_key:
            st.warning("⚠️ 請先於左側輸入必要的 API Key。")
            st.stop()

        with st.status("🚀 戰情室啟動中...", expanded=True) as status:
            st.write("📡 正在抓取市場報價與板塊數據...")
            st.write("⏰ 正在抓取盤前期貨動態...")
            st.write("🔍 Gemini 正在搜尋今日財經新聞...")
            st.write("🤖 AI 正在生成盤前解說與策略...")

            market_data = _fetch_all_data(
                watchlist_symbols=watchlist_symbols,
                fred_api_key=fred_api_key,
                gemini_api_key=gemini_api_key,
                openai_api_key=openai_api_key,
            )

            if _has_valid_cache_guard_data(market_data):
                st.session_state["market_data"] = market_data
                st.session_state["last_updated"] = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
                status.update(label="✅ 戰報生成完畢！數據已快取。", state="complete", expanded=False)
            else:
                status.update(label="⚠️ 核心數據不完整，未更新快取。", state="error", expanded=False)

            _render_all_tabs(market_data)


if __name__ == "__main__":
    main()

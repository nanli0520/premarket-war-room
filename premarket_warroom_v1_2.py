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

NO_VOLUME_SYMBOLS = {"^VIX", "DX-Y.NYB", "^GSPC", "^IXIC", "^DJI"}
CACHE_GUARD_SYMBOLS = ["SPY", "QQQ", "^VIX"]
DEFAULT_AI_RESPONSE = "目前無法連線至 AI 獲取解說，請依上方數據自行判斷。"

SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLI", "XLV", "XLY"]
SECTOR_NAMES = {
    "XLK": "科技",
    "XLE": "能源",
    "XLF": "金融",
    "XLI": "工業",
    "XLV": "醫療",
    "XLY": "非必需消費",
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


def calc_watchlist_stats(df: pd.DataFrame) -> dict[str, Any] | None:
    """計算觀察股均線、支撐壓力統計，失敗回傳 None。"""
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

        return {
            "現價": round(latest_close, 2),
            "日漲跌(%)": round(day_pct, 2) if isinstance(day_pct, (int, float)) else "N/A",
            "MA20": round(ma20, 2) if pd.notna(ma20) else "N/A",
            "距MA20(%)": round(ma20_pct, 2) if ma20_pct is not None else "N/A",
            "支撐位": round(support, 2) if pd.notna(support) else "N/A",
            "距支撐(%)": round(dist_support_pct, 2) if dist_support_pct is not None else "N/A",
            "壓力位": round(resistance, 2) if pd.notna(resistance) else "N/A",
            "距壓力(%)": round(dist_resistance_pct, 2) if dist_resistance_pct is not None else "N/A",
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


def resolve_ai_provider(api_key: str, user_selection: str) -> str:
    """依 sidebar 選擇決定 Provider，或根據 Key 前綴自動偵測。"""
    if user_selection == "OpenAI":
        return "openai"
    if user_selection == "Google Gemini":
        return "gemini"
    return "openai" if api_key.startswith("sk-") else "gemini"


def build_ai_prompt(data: dict[str, Any]) -> str:
    """動態組裝規格定義的 User Prompt。"""
    return (
        "請基於以下昨日美股收盤數據，用繁體中文撰寫：\n"
        "1. 一段「盤前白話解說」（100字以內，解釋今天市場在演什麼、為什麼）\n"
        "2. 一句「今日操作策略」（20字以內，具備防呆性質）\n\n"
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
        "[盤前解說]：...\n"
        "[今日策略]：..."
    )


def call_ai_analysis(api_key: str, provider: str, prompt: str) -> str:
    """呼叫 OpenAI 或 Gemini，失敗回傳預設訊息。"""
    system_prompt = (
        "你是一位冷靜、重風險控管的美股波段交易員，擅長用最簡單的語言解釋市場。"
        "你服務的對象是剛入市的小資族新手，因此你的語言必須："
        "- 避免專業術語（若使用必須立刻用括號解釋）"
        "- 不誇大、不預測未來"
        "- 強調風險控管，在 Risk-Off 環境下主動建議「多看少做」"
        "- 說明「為什麼」資金在移動，不只說「資金從A流向B」"
    )

    try:
        if provider == "openai":
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 220,
                },
                timeout=20,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return text if text and text.strip() else DEFAULT_AI_RESPONSE

        # Gemini REST API
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 220},
        }
        resp = requests.post(endpoint, json=payload, timeout=20)
        resp.raise_for_status()
        candidates = resp.json().get("candidates", [])
        if not candidates:
            return DEFAULT_AI_RESPONSE
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts)
        return text if text and text.strip() else DEFAULT_AI_RESPONSE
    except Exception:
        return DEFAULT_AI_RESPONSE


# 7) Session Cache Layer

def _fetch_all_data(
    watchlist_symbols: list[str],
    fred_api_key: str,
    ai_api_key: str,
    provider_choice: str,
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
        except Exception:
            pct_changes[symbol] = None

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

    fred_details = fetch_fred_us10y_details(fred_api_key)
    market_data["us10y"] = fred_details

    btc_data = fetch_binance_btc()
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
            "狀態": "N/A",
        }
        try:
            df = price_data.get(symbol)
            if df is not None:
                stats = calc_watchlist_stats(df)
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

    if ai_api_key:
        try:
            provider = resolve_ai_provider(ai_api_key, provider_choice)
            ai_prompt = build_ai_prompt(market_data)
            ai_response = call_ai_analysis(ai_api_key, provider, ai_prompt)
            market_data["ai_response"] = ai_response or DEFAULT_AI_RESPONSE
        except Exception:
            market_data["ai_response"] = DEFAULT_AI_RESPONSE
    else:
        market_data["ai_response"] = ""

    return market_data


# 8) Streamlit UI Rendering

def _fmt_metric_value(value: float | str | None, prefix: str = "") -> str:
    if isinstance(value, (int, float)):
        return f"{prefix}{value:,.2f}"
    return "N/A"


def _fmt_delta(value: float | str | None) -> str:
    if isinstance(value, (int, float)):
        return f"{value:+.2f}%"
    return "N/A"


def _regime_badge(regime: str) -> str:
    mapping = {
        "Risk-Off": "🔴 Risk-Off（極端恐慌）",
        "Liquidity Contraction": "⚠️ Liquidity Contraction（流動性收縮）",
        "High Volatility Risk-Off": "🟠 High Vol Risk-Off（高波動風險趨避）",
        "Risk-On": "🟢 Risk-On（風險偏好）",
        "Range Market": "🟡 Range Market（震盪盤整）",
    }
    return mapping.get(regime, f"🟡 {regime}")


def _render_all_tabs(data: dict[str, Any]) -> None:
    tab1, tab2, tab3, tab4 = st.tabs([
        "🌡️ 市場戰情總覽",
        "🔍 結構分析",
        "🔄 資金輪動雷達",
        "🎯 觀察股雷達",
    ])

    with tab1:
        st.markdown(f"## {_regime_badge(data.get('market_regime', 'Range Market'))}")
        st.divider()

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
                title="六大板塊 ETF 單日漲跌幅",
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
        watchlist_rows = data.get("watchlist", [])
        watch_df = pd.DataFrame(watchlist_rows)
        if not watch_df.empty:
            def _style_status(val: Any) -> str:
                if val == "📈 偏強":
                    return f"color: {UP_COLOR}; font-weight: bold;"
                if val == "📉 偏弱":
                    return f"color: {DOWN_COLOR}; font-weight: bold;"
                if val == "➡️ 中性":
                    return f"color: {NEUTRAL_COLOR}; font-weight: bold;"
                return ""

            styled = watch_df.style.map(_style_status, subset=["狀態"])
            st.dataframe(styled, use_container_width=True)
        else:
            st.info("尚無觀察股資料。")

        with st.expander("📄 查看原始數據（偵錯用）"):
            st.dataframe(pd.DataFrame(data.get("raw_data", [])), use_container_width=True)


# 9) Main Application Entry

def main() -> None:
    st.set_page_config(page_title="專屬盤前戰情室 V1.2", layout="wide")

    st.header("🚦 專屬盤前戰情室 V1.2", divider="rainbow")

    st.sidebar.header("📊 War Room Setup", divider="rainbow")
    provider_choice = st.sidebar.selectbox(
        "🤖 AI Provider",
        options=["🔍 自動偵測（依 Key 前綴）", "OpenAI", "Google Gemini"],
        index=0,
    )

    ai_api_key = st.sidebar.text_input("請輸入 OpenAI 或 Gemini API Key", type="password")
    fred_api_key = st.sidebar.text_input("請輸入 FRED API Key", type="password")
    st.sidebar.caption("💡 請先輸入 Key，再點擊更新按鈕")
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

        with st.spinner("⏳ 聯網抓取市場數據與 AI 分析中，請稍候..."):
            market_data = _fetch_all_data(
                watchlist_symbols=watchlist_symbols,
                fred_api_key=fred_api_key,
                ai_api_key=ai_api_key,
                provider_choice=provider_choice,
            )

            if all(market_data.get(sym) is not None for sym in CACHE_GUARD_SYMBOLS):
                st.session_state["market_data"] = market_data
                st.session_state["last_updated"] = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
                st.success("✅ 戰報生成完畢！數據已快取。")
            else:
                st.warning("⚠️ 本次核心數據抓取不完整，未更新快取。上方顯示上次有效數據。")

            _render_all_tabs(market_data)


if __name__ == "__main__":
    main()

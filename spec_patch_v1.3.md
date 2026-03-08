# 《盤前戰情室 V1.3》修改補丁說明書
# Pre-Market War Room — V1.3 Patch Spec

> **基礎版本**：V1.2.1（`premarket_warroom_v1_2_1.py`）
> **原始規格**：`spec_premarket_warroom_v1.2.md`
> **版本**：V1.3 Patch | **日期**：2026-03-08
> **修改主題**：讓燈號變成一句話，讓數字連動行動 + AI 雙模型新聞感知升級

> **⚠️ AI 實作指令**：請同時提供本補丁說明書與原始規格書（`spec_premarket_warroom_v1.2.md`）及現有程式碼（`premarket_warroom_v1_2_1.py`）給 AI。以本補丁說明書為優先修改依據，原始規格書作為「不動部分」的守護參考。

---

## 🚫 絕對守護邊界（嚴禁修改）

以下架構為 V1.2 核心設計，任何新功能均不得影響這些部分：

| 守護項目 | 位置 | 原因 |
|---|---|---|
| F-008 隔離式 try-except 架構 | `_fetch_all_data()` 內每個外部呼叫 | 防止單一失敗導致白屏 |
| `price_data` 字典為區域變數 | `_fetch_all_data()` 內部 | 防止 Session State 記憶體膨脹 |
| Session State 快取守衛邏輯 | `_has_valid_cache_guard_data()` | 防止部分失敗污染快取 |
| `determine_market_regime()` 判定規則 | 五層優先順序，含 `vix_val > 30` 保底 | 核心判定邏輯不可由 AI 修改 |
| `NO_VOLUME_SYMBOLS` 白名單 | 全域常數 | VIX/DXY 的 Volume 過濾保護 |
| `CACHE_GUARD_SYMBOLS` | 全域常數 | SPY/QQQ/VIX 三項核心守衛 |
| 程式入口結構（F-007）| `main()` 函數 | 按鈕外渲染快取 / 按鈕內更新數據 |

---

## 📦 第一批修改（優先實作）

### [MODIFY] F-001：Sidebar 雙 API Key 輸入區

**修改說明**：V1.2 Sidebar 只有一個 AI API Key 輸入欄 + Provider 選擇器。V1.3 改為兩個獨立 Key 輸入欄，系統自動分工，不需使用者手動選 Provider。

**舊設計**（移除）：
```python
provider_choice = st.sidebar.selectbox("🤖 AI Provider", ...)
ai_api_key = st.sidebar.text_input("請輸入 OpenAI 或 Gemini API Key", ...)
```

**新設計**（取代）：
```python
# V1.3：雙 Key 輸入，系統自動分工
gemini_api_key = st.sidebar.text_input(
    "🔍 Gemini API Key（新聞搜尋主力）",
    type="password",
    help="用於 Google Search Grounding 自動搜尋今日財經新聞"
)
openai_api_key = st.sidebar.text_input(
    "🤖 OpenAI API Key（分析備援）",
    type="password",
    help="用於白話解說主力分析，Gemini 失敗時自動接手"
)
```

**說明文字**（sidebar 加入）：
```
💡 兩個 Key 均非必填：
   • 僅填 Gemini Key → 啟用新聞搜尋 + AI 分析
   • 僅填 OpenAI Key → 啟用純數據 AI 分析（無新聞）
   • 兩個都填 → 最完整體驗（Gemini 主力，OpenAI 備援）
   • 都不填 → 系統以規則引擎運作，不呼叫 AI
```

---

### [NEW] 全域常數新增

在程式頂部全域配置區新增：

```python
# V1.3 新增：盤前期貨標的（不需要 Volume 過濾）
FUTURES_SYMBOLS = ["ES=F", "NQ=F", "VX=F"]
NO_VOLUME_SYMBOLS = {"^VIX", "DX-Y.NYB", "^GSPC", "^IXIC", "^DJI",
                     "ES=F", "NQ=F", "VX=F"}  # 擴充：加入期貨

# V1.3 新增：行動建議框規則配置
REGIME_ACTION_MAP = {
    "Risk-Off": {
        "color": "#B71C1C",  # 深紅
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
```

---

### [MODIFY] F-006：AI 分析功能升級（雙模型 + 新聞脈絡）

**修改說明**：V1.2 的 `call_ai_analysis()` 只支援單一模型、單一呼叫、兩段輸出。V1.3 改為兩階段呼叫 + 三層降級 + 三段輸出。

#### 新增函數：`fetch_news_context()`

```python
def fetch_news_context(gemini_api_key: str) -> str:
    """
    使用 Gemini Search Grounding 搜尋今日財經新聞摘要。
    回傳 50 字以內的新聞摘要字串，失敗回傳空字串（不拋出例外）。
    """
    if not gemini_api_key:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")  # 若失敗可嘗試 gemini-2.5-flash
        
        news_prompt = (
            "請用繁體中文，用50字以內，列出最近1-2則"
            "最可能直接影響美國科技股或整體大盤的重大財經新聞事件。"
            "只列事件本身，不要解釋，不要加標點以外的格式。"
        )
        response = model.generate_content(
            news_prompt,
            tools=[{"google_search": {}}]
        )
        news_text = response.text.strip() if response.text else ""
        return news_text[:200]  # 安全截斷，避免過長
    except Exception:
        return ""  # 失敗靜默，不影響主流程
```

#### 修改函數：`call_ai_analysis()`

**V1.3 三層降級架構**：

```python
def call_ai_analysis(
    gemini_api_key: str,
    openai_api_key: str,
    prompt: str,
    news_context: str,
) -> str:
    """
    V1.3 三層降級 AI 分析：
    Layer 1：OpenAI gpt-5-mini（主力分析，額度最大）
    Layer 2：Gemini（gemini-2.0-flash）純文字降級
    Layer 3：DEFAULT_AI_RESPONSE（兜底）
    """
    # --- Layer 1：OpenAI gpt-5-mini 主力 ---
    if openai_api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_api_key)
            full_prompt = prompt
            if news_context:
                full_prompt += f"\n\n近期重大財經事件（由 Google 搜尋取得）：\n{news_context}"
            
            response = client.chat.completions.create(
                model="gpt-5-mini",  # 依帳戶調整，可改為 gpt-4o-mini 等
                messages=[
                    {"role": "system", "content": (
                        "你是一位冷靜、重風險控管的美股波段交易員，"
                        "擅長用最簡單的語言解釋市場給新手聽。"
                        "不誇大、不預測未來、強調風險控管。"
                    )},
                    {"role": "user", "content": full_prompt},
                ],
                max_tokens=300,
                temperature=0.4,
            )
            result = response.choices[0].message.content.strip()
            if result:
                return result
        except Exception:
            pass  # 失敗繼續降級

    # --- Layer 2：Gemini 純文字降級（不搜尋，僅分析）---
    if gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel("gemini-3-flash-preview")  # 若失敗可嘗試 gemini-2.5-flash
            full_prompt = prompt
            if news_context:
                full_prompt += f"\n\n近期重大財經事件：\n{news_context}"
            response = model.generate_content(full_prompt)
            result = response.text.strip() if response.text else ""
            if result:
                return result
        except Exception:
            pass

    # --- Layer 3：終極兜底 ---
    return DEFAULT_AI_RESPONSE
```

#### 修改：`build_ai_prompt()`

在現有 prompt 後增加第三段輸出指令：

```python
# V1.3 新增輸出格式（在現有兩段後加第三段）
output_format = """
輸出格式（請嚴格遵守，不要加任何 Markdown 標題）：
[盤前解說]：...（100字以內，解釋今天市場在演什麼、為什麼）
[今日策略]：...（20字以內，具備防呆性質）
[事件脈絡]：...（50字以內，說明近期事件對哪個板塊有影響，若無新聞資訊則填「無特殊事件，以數據為主要依據」）
"""
```

#### 修改：`_fetch_all_data()` 中的 AI 呼叫段落

```python
# V1.3：先搜尋新聞，再呼叫主力分析（兩步驟，均獨立隔離）

# Step 1：Gemini 搜尋新聞（獨立隔離，失敗不影響後續）
try:
    news_context = fetch_news_context(gemini_api_key)
except Exception:
    news_context = ""

# Step 2：主力分析（三層降級）
try:
    ai_response = call_ai_analysis(
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        prompt=build_ai_prompt(data),
        news_context=news_context,
    )
    if not ai_response or not ai_response.strip():
        ai_response = DEFAULT_AI_RESPONSE
except Exception:
    ai_response = DEFAULT_AI_RESPONSE
```

---

### [NEW] 頂部「今日行動建議框」

**位置**：`_render_all_tabs()` 函數最頂部，在 `st.tabs()` 創建之前渲染（所有 Tab 共用可見）。

**新增函數**：`_render_action_banner(data: dict)`

```python
def _render_action_banner(data: dict) -> None:
    """
    根據 Market Regime 和觀察股狀態，渲染頂部行動建議框。
    完全使用規則引擎，零 API 費用。
    """
    regime = data.get("regime", "Range Market")
    config = REGIME_ACTION_MAP.get(regime, REGIME_ACTION_MAP["Range Market"])
    
    # 主橫幅
    st.markdown(f"""
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
    """, unsafe_allow_html=True)
    
    # 觀察股快速掃描（從 watchlist_stats 取值）
    watchlist_stats = data.get("watchlist_stats", {})
    if watchlist_stats:
        worth_watching = []
        need_caution = []
        
        for symbol, stats in watchlist_stats.items():
            if stats is None:
                continue
            ma20_pct = stats.get("距MA20(%)")
            dist_support = stats.get("距支撐(%)")
            status = stats.get("狀態", "")
            
            if not isinstance(ma20_pct, (int, float)):
                continue
            
            # 偏強且距支撐 < 8%（有買點空間）
            if "偏強" in status and isinstance(dist_support, (int, float)) and dist_support < 8:
                worth_watching.append(f"**{symbol}**（偏強，距支撐 {dist_support:.1f}%）")
            # 偏弱（需要警覺）
            elif "偏弱" in status:
                need_caution.append(f"**{symbol}**（偏弱，距MA20 {ma20_pct:.1f}%）")
        
        col1, col2 = st.columns(2)
        with col1:
            if worth_watching:
                st.markdown("📍 **可關注**：" + "、".join(worth_watching[:3]))
            else:
                st.markdown("📍 **可關注**：目前無明顯機會標的")
        with col2:
            if need_caution:
                st.markdown("⚠️ **需警覺**：" + "、".join(need_caution[:3]))
            else:
                st.markdown("⚠️ **需警覺**：觀察股整體穩定")
        
        st.divider()
```

**呼叫位置**（`_render_all_tabs()` 頂部）：

```python
def _render_all_tabs(data: dict) -> None:
    # V1.3 新增：行動建議框（在 Tabs 之前）
    _render_action_banner(data)
    
    # 以下保持 V1.2 原有的 st.tabs() 結構...
    tab1, tab2, tab3, tab4 = st.tabs([...])
```

---

### [MODIFY] Tab 1：Regime 視覺衝擊升級

**修改說明**：將 `_regime_badge()` 函數從小 badge 升級為全幅大橫幅。

**修改 `_regime_badge()` 函數**：

```python
def _regime_badge(regime: str) -> None:
    """V1.3：全幅彩色 Regime 橫幅，讓使用者第一眼就感受到市場狀態。"""
    config_map = {
        "Risk-Off":                  ("🔴", "#B71C1C", "#FFCDD2"),
        "Liquidity Contraction":     ("🔴", "#C62828", "#FFEBEE"),
        "High Volatility Risk-Off":  ("🟠", "#E65100", "#FFF3E0"),
        "Risk-On":                   ("🟢", "#1B5E20", "#E8F5E9"),
        "Range Market":              ("🟡", "#37474F", "#ECEFF1"),
    }
    icon, color, bg = config_map.get(regime, ("⚪", "#333", "#F5F5F5"))
    
    st.markdown(f"""
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
    """, unsafe_allow_html=True)
```

---

### [MODIFY] Tab 4：觀察股雷達 UI 升級

**修改說明**：解決小數點問題 + 加入 Top-Down 環境連動警示。

#### 小數點格式化

```python
# V1.3：使用 st.column_config 統一格式化
# 注意：N/A 字串欄位在傳入前需先轉為 float("nan")

def _clean_watchlist_df(raw_data: list[dict]) -> pd.DataFrame:
    """將 N/A 字串轉為 NaN，確保 column_config 能正確格式化。"""
    df = pd.DataFrame(raw_data)
    numeric_cols = ["現價", "MA20", "距MA20(%)", "支撐位", "距支撐(%)", "壓力位", "距壓力(%)"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# st.dataframe 呼叫方式
st.dataframe(
    df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "現價":      st.column_config.NumberColumn("現價", format="$%.2f"),
        "MA20":      st.column_config.NumberColumn("MA20", format="$%.2f"),
        "距MA20(%)": st.column_config.NumberColumn("距MA20(%)", format="%.2f%%"),
        "支撐位":    st.column_config.NumberColumn("支撐位", format="$%.2f"),
        "距支撐(%)": st.column_config.NumberColumn("距支撐(%)", format="%.2f%%"),
        "壓力位":    st.column_config.NumberColumn("壓力位", format="$%.2f"),
        "距壓力(%)": st.column_config.NumberColumn("距壓力(%)", format="%.2f%%"),
        "日漲跌(%)": st.column_config.NumberColumn("日漲跌(%)", format="%.2f%%"),
    }
)
```

#### Top-Down 環境連動警示

在 Tab 4 `st.dataframe()` 上方加入：

```python
# V1.3：Top-Down 環境連動警示
regime = data.get("regime", "Range Market")
if regime in ["Risk-Off", "Liquidity Contraction"]:
    st.error(
        f"⚠️ **{regime} 環境警示**：大環境風險偏高，觀察股中所有標的暫停追高。"
        "有浮盈倉位請提高警覺，等待環境改善再行動。"
    )
elif regime == "High Volatility Risk-Off":
    st.warning(
        "🟠 **高波動環境**：個股操作建議輕倉，等待大環境明確後再加碼。"
    )
elif regime == "Risk-On":
    st.success(
        "🟢 **Risk-On 環境**：可關注觀察股中偏強、靠近支撐位的標的，嚴設停損。"
    )
```

---

## 📦 第二批修改（期貨盤前感知）

### [NEW] 全域常數新增

```python
# 盤前期貨標的（已在第一批加入 NO_VOLUME_SYMBOLS）
FUTURES_SYMBOLS = ["ES=F", "NQ=F", "VX=F"]
FUTURES_NAMES = {
    "ES=F": "S&P 期貨",
    "NQ=F": "NASDAQ 期貨",
    "VX=F": "VIX 期貨",
}
```

### [NEW] 新增函數：`fetch_premarket_futures()`

```python
def fetch_premarket_futures() -> dict[str, dict]:
    """
    抓取盤前期貨今日累積漲跌幅。
    使用分鐘線抓取今日數據，計算第一筆到最後一筆的累積變化。
    失敗回傳空字典。
    """
    results = {}
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
                "price": round(last_price, 2),
                "pct": round(pct, 2),
                "time": df.index[-1].strftime("%H:%M ET") if hasattr(df.index[-1], "strftime") else "N/A",
            }
        except Exception:
            results[symbol] = None
    return results
```

### [MODIFY] `_fetch_all_data()` — 新增期貨抓取

```python
# 在現有抓取完成後，新增期貨段落（獨立隔離）
try:
    futures_data = fetch_premarket_futures()
except Exception:
    futures_data = {}

# 加入回傳字典
data["futures_data"] = futures_data
```

### [NEW] Tab 1：盤前期貨感知區顯示

在 Tab 1 的 Regime Badge 下方、`st.metric()` 四欄之前加入：

```python
# V1.3：盤前期貨感知區
futures = data.get("futures_data", {})
if any(futures.get(s) for s in FUTURES_SYMBOLS):
    st.caption("⏰ 盤前期貨動態（今日開盤以來累積）")
    fut_cols = st.columns(len(FUTURES_SYMBOLS))
    for i, symbol in enumerate(FUTURES_SYMBOLS):
        f = futures.get(symbol)
        name = FUTURES_NAMES[symbol]
        with fut_cols[i]:
            if f:
                delta_str = f"{f['pct']:+.2f}%"
                st.metric(
                    label=f"{name}（{symbol}）",
                    value=f"${f['price']:,.1f}" if symbol != "VX=F" else f"{f['price']:.1f}",
                    delta=delta_str,
                )
            else:
                st.metric(label=name, value="N/A", delta=None)
    st.divider()
```

---

## 📦 第三批增補條款（仲裁審查後採用）

> 以下三項為三方仲裁審查後決議採用，標為獨立批次以便 AI 辨識修改範圍，不與前兩批混淆。

---

### [MODIFY] Tab 3：SECTOR_ETFS 納入 SMH 顯示

**修改說明**：SMH 已在 `CORE_MARKET_SYMBOLS` 中每次抓取，只需加入板塊輪動排序，零額外 API 呼叫成本。

```python
# 修改全域常數（僅此兩行，其餘不動）
SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLI", "XLV", "XLY", "SMH"]
SECTOR_NAMES = {
    "XLK": "科技", "XLE": "能源", "XLF": "金融",
    "XLI": "工業", "XLV": "醫療", "XLY": "非必需消費",
    "SMH": "半導體",  # V1.3 新增，已在核心抓取清單，無額外費用
}
```

---

### [MODIFY] Tab 4：觀察股雷達新增 ATR(14) 與 RS vs SPY

**修改說明**：利用現有 `price_data` 的 OHLCV 計算 ATR(14)，利用已計算的 `spy_pct` 計算相對強度，零額外 API 呼叫。

**ATR 意義**：14 日平均波幅，告訴你這支股票「正常一天可能動多少」，用於判斷停損距離。
**RS vs SPY 意義**：`個股單日漲跌幅 − SPY 單日漲跌幅`（明確定義，防止 AI 自由發揮成其他算法）。正值 = 比大盤強，負值 = 跑輸大盤。

#### 修改 `calc_watchlist_stats()` 函數簽名與計算邏輯

```python
def calc_watchlist_stats(df: pd.DataFrame, spy_pct: float | None = None) -> dict | None:
    """
    V1.3 新增 spy_pct 參數，用於計算 RS vs SPY。
    原有所有計算邏輯保持不變，在 return 前新增以下兩段：
    """
    # ... 前方現有計算邏輯完全不動 ...

    # V1.3 新增 1：ATR(14) 計算
    try:
        high = df["High"].tail(15)
        low = df["Low"].tail(15)
        close_prev = df["Close"].tail(15).shift(1)
        tr = pd.concat(
            [high - low, (high - close_prev).abs(), (low - close_prev).abs()],
            axis=1
        ).max(axis=1)
        atr = round(tr.tail(14).mean(), 2)
    except Exception:
        atr = None

    # V1.3 新增 2：RS vs SPY（定義：個股單日漲跌幅 − SPY 單日漲跌幅）
    stock_pct = (df["Close"].iloc[-1] - df["Close"].iloc[-2]) / df["Close"].iloc[-2] * 100 \
        if len(df) >= 2 and df["Close"].iloc[-2] != 0 else None
    if isinstance(stock_pct, float) and isinstance(spy_pct, float):
        rs_vs_spy = round(stock_pct - spy_pct, 2)
    else:
        rs_vs_spy = None

    # 在原有 return dict 末尾加入兩個新欄位
    return {
        # ... 原有所有欄位保持不動 ...
        "ATR(14)": round(atr, 2) if atr is not None else "N/A",
        "RS vs SPY": f"{rs_vs_spy:+.2f}%" if rs_vs_spy is not None else "N/A",
    }
```

#### 修改呼叫位置（`_fetch_all_data()` 內的觀察股計算段落）

```python
# 呼叫時傳入 spy_pct（已在 _fetch_all_data() 中計算好）
stats = calc_watchlist_stats(price_data[symbol], spy_pct=spy_pct)
```

#### Tab 4 的 `st.column_config` 同步新增格式化

```python
column_config={
    # ... 原有欄位不動 ...
    "ATR(14)":    st.column_config.NumberColumn("ATR(14)", format="$%.2f",
                      help="14日平均波幅，代表該股正常一日可能的價格波動範圍"),
    "RS vs SPY":  st.column_config.TextColumn("RS vs SPY",
                      help="個股單日漲跌幅 − SPY 單日漲跌幅，正值表示跑贏大盤"),
}
```

---

### [MODIFY] main()：按鈕區塊改用 `st.status`；Tab 1 期貨區加 caption 說明

**修改說明 1**：V1.3 執行鏈加入新聞搜尋與期貨抓取，等待時間從約 5 秒拉長至 15~20 秒，改用 `st.status` 讓使用者看到逐步進度，消除「是否卡死」的焦慮。

```python
# main() 中按鈕點擊區塊修改
if st.button("🔄 獲取最新盤前戰報", use_container_width=True):
    with st.status("🚀 戰情室啟動中...", expanded=True) as status:
        st.write("📡 正在抓取市場報價與板塊數據...")
        # ... yfinance 抓取迴圈 ...

        st.write("⏰ 正在抓取盤前期貨動態...")
        # ... fetch_premarket_futures() ...

        st.write("🔍 Gemini 正在搜尋今日財經新聞...")
        # ... fetch_news_context() ...

        st.write("🤖 AI 正在生成盤前解說與策略...")
        # ... call_ai_analysis() ...

        # 快取守衛判斷（邏輯不動）
        if _has_valid_cache_guard_data(market_data):
            st.session_state["market_data"] = market_data
            st.session_state["last_updated"] = (
                datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
            )
            status.update(label="✅ 戰報生成完畢！數據已快取。", state="complete", expanded=False)
        else:
            status.update(label="⚠️ 核心數據不完整，未更新快取。", state="error", expanded=False)

        _render_all_tabs(market_data)
```

**修改說明 2**：期貨感知區的 caption 說明加入認知校正文字（防止使用者誤解小數字代表數據異常）。

```python
# Tab 1 期貨感知區的 caption 修改為：
st.caption(
    "⏰ 盤前期貨動態（今日期貨開盤以來累積，**非昨收基準**）"
    "　｜　數字小代表今日盤前平靜，不代表數據異常"
)
```

---

---

## 📦 第五批：AI 輸出三段分離顯示（Claude 審查後採用）

---

### [MODIFY] Tab 1：AI 回傳三段文字拆開分別顯示

**問題**：`[事件脈絡]` 新輸出段落目前在 prompt 有定義，但規格未說明顯示位置。三段黏在一起顯示會讓新手混亂，不知道哪段是「市場狀況」、哪段是「我的行動」、哪段是「事件背景」。

**新增輔助函數**：`_parse_ai_response()`

```python
def _parse_ai_response(raw: str) -> dict[str, str]:
    """
    解析 AI 回傳的三段格式化輸出。
    格式：[盤前解說]：... \n [今日策略]：... \n [事件脈絡]：...
    解析失敗時，整段放入 '盤前解說'，其餘為空，確保不白屏。
    """
    result = {"盤前解說": "", "今日策略": "", "事件脈絡": ""}
    try:
        import re
        pattern = r"\[([^\]]+)\]：(.+?)(?=\[|$)"
        matches = re.findall(pattern, raw, re.DOTALL)
        for key, value in matches:
            key = key.strip()
            if key in result:
                result[key] = value.strip()
        if not any(result.values()):
            result["盤前解說"] = raw.strip()
    except Exception:
        result["盤前解說"] = raw.strip()
    return result
```

**修改 Tab 1 的 AI 解說顯示段落**（取代原本單一 `st.info()`）：

```python
parsed = _parse_ai_response(data.get("ai_response", DEFAULT_AI_RESPONSE))

if parsed["盤前解說"]:
    st.info(f"📰 **盤前解說**\n\n{parsed['盤前解說']}")

if parsed["今日策略"]:
    st.success(f"🎯 **今日策略**：{parsed['今日策略']}")

if parsed["事件脈絡"]:
    st.markdown(
        f"""<div style="border:1px solid #ccc; border-radius:6px;
                        padding:10px 14px; background:#FAFAFA; font-size:13px;">
            🌐 <strong>事件脈絡</strong>（來源：AI 即時搜尋）<br>{parsed['事件脈絡']}
        </div>""",
        unsafe_allow_html=True
    )
elif not parsed["盤前解說"] and not parsed["今日策略"]:
    st.info(DEFAULT_AI_RESPONSE)
```

**視覺語意**：藍框（市場資訊）→ 綠框（行動指引）→ 灰框（事件背景）

---

## 📦 第四批：地雷修補（Claude 審查後採用）

> 以下兩項為 Claude 架構審查發現的真實邏輯缺口，屬於必修項目。

---

### [MODIFY] `fetch_news_context()`：失敗改為可見提示

**問題**：目前 `except Exception: return ""` 完全靜默，使用者無法分辨「今天無重大新聞」與「API 根本沒執行成功」。

**修改**：將 except 區塊改為在 sidebar 顯示小型提示：

```python
except Exception as e:
    # 靜默失敗，但在 sidebar 顯示提示讓使用者知道原因
    try:
        st.sidebar.caption(f"⚠️ 新聞搜尋不可用：{type(e).__name__}")
    except Exception:
        pass  # sidebar 本身若失敗也不影響主流程
    return ""
```

**注意**：`st.sidebar.caption` 放在 except 內部，也需要用 try-except 包住，避免在快取渲染（按鈕外）時觸發 sidebar 衝突。

---

### [MODIFY] `_render_action_banner()`：高風險環境強制清空「可關注」清單

**問題**：Risk-Off 環境下，頂部橫幅說「全場旁觀」，但行動建議框仍可能顯示「📍 可關注：PLTR」，兩個訊號互相矛盾，新手容易誤判。

**修改**：在 `worth_watching` 填充邏輯前加入環境濾鏡：

```python
# 在 _render_action_banner() 的觀察股掃描區塊修改
col1, col2 = st.columns(2)
with col1:
    # V1.3 地雷修補：高風險環境強制鎖定可關注清單
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
```

**設計邏輯**：Risk-Off / Liquidity Contraction 環境下，`worth_watching` 的計算仍執行（不浪費），只是在渲染層強制覆蓋顯示，確保 Top-Down 一致性：
- 頂部橫幅說「旁觀」→ 個股建議框也說「暫停關注」
- 不發生「系統一邊叫你跑、一邊叫你買」的矛盾訊號

---

## 📋 V1.4 待辦清單（本次不實作，記錄備查）

| 功能 | 說明 | 來源 |
|---|---|---|
| 每日戰報 JSON 紀錄 | 每次生成戰報時儲存 Regime + 日期到本地 JSON，一個月後可回顧「Liquidity Contraction 後市場實際怎麼走」，建立歷史盤感 | Claude 審查建議 |
| 板塊清單擴充（IGV / ITA） | AI 新聞層完成後，補充事件敏感板塊 ETF | 本次仲裁記錄 |
| Market Regime 加入 DXY 流動性引擎 | 需獨立三方審議，屬架構性改動 | GPT 建議，本次駁回 |

---

## 🔧 技術實作要求

### 新增套件

```bash
# 已有套件，無需新增
# google-generativeai 已在 V1.2 中引入
# openai 已在 V1.2 中引入
```

### 函數簽名變更

| 函數 | V1.2 | V1.3 |
|---|---|---|
| `_fetch_all_data()` | `(watchlist, fred_key, ai_key, provider)` | `(watchlist, fred_key, gemini_key, openai_key)` |
| `call_ai_analysis()` | `(api_key, provider, prompt)` | `(gemini_key, openai_key, prompt, news_context)` |
| `_render_all_tabs()` | `(data)` | `(data)` — 不變，但內部新增呼叫 |

### Gemini 模型名稱確認

> ✅ **已確認（截圖核實）**：正確的 API model ID 為 **`gemini-3-flash-preview`**。
> Google 命名慣例省略「.0」，且 Gemini 3 系列目前為預覽階段，需加 `-preview` 後綴。
> 若呼叫失敗，降級備案依序嘗試：
> 1. `"gemini-2.5-flash"`
> 2. `"gemini-2.0-flash"`

### OpenAI 模型名稱確認

> ⚠️ 你的帳戶截圖顯示有 gpt-5-mini（250萬 tokens/天）。
> 在程式中使用 `"gpt-5-mini"`，若呼叫失敗可降級為 `"gpt-4o-mini"`。

---

## ✅ AI 實作守則（給代入程式碼的 AI 看）

1. **保留所有 V1.2 現有功能**：本補丁列出的是新增與修改，未提及的一律不動
2. **守護邊界優先**：補丁頂部的「絕對守護邊界」表格為最高優先，任何新功能不得違反
3. **隔離保護延伸**：所有新增的外部 API 呼叫（`fetch_news_context`、`fetch_premarket_futures`）必須獨立 try-except 隔離
4. **N/A 顯示規則**：新功能中任何欄位取不到數值，顯示 `"N/A"`，不拋出例外，不中斷渲染
5. **繁體中文註釋**：所有新增程式碼加清楚的繁體中文說明
6. **不重寫、只修改**：根據本補丁精準修改對應位置，不要重構整個檔案

---

*補丁版本：V1.3 | 基礎系統：premarket_warroom_v1_2_1.py | 日期：2026-03-08*

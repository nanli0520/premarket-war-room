# 《盤前戰情室 V1.2》規格說明書
# Pre-Market War Room — AI 可執行版 Spec

> **版本**：V1.2 | **更新日期**：2026-03-08
> **變更摘要**：基於三方模型共識審議（Gemini / GPT-OSS / Claude），修正 1 個致命缺陷、4 個中等風險、4 個低風險問題。
> 新增 VIX 成交量過濾修正、Regime 第 1 層絕對值保底條件、Session State 寫入安全守衛、程式入口流程明確化、`DATA_PERIODS` 集中配置。
>
> **用途說明**：本規格說明書作為 AI 提示語使用。
> 將此完整內容提交給任何 AI（GPT / Gemini / Claude），
> AI 將根據規格直接生成完整、可執行的 Streamlit 程式碼。

---

## 📋 系統概述

### 系統名稱

【個人專屬】盤前戰情室 V1.2（Pre-Market War Room）

### 核心功能描述

建立一個基於網頁的個人化盤前市場分析儀表板，能夠：

1. 一鍵自動抓取美股核心市場數據（指數、VIX、美債、原油、板塊 ETF、個股）
2. 根據固定規則，自動判定當日市場狀態（Market Regime）— 五層優先順序，含極端 VIX 保底條件
3. 自動判斷本次下跌是「情緒洗盤」還是「結構性風險」，並輸出中文邏輯解說
4. 掃描主要板塊 ETF，呈現資金輪動方向
5. 監控個人觀察股距離均線、支撐位與壓力位的位置
6. 使用規則模板引擎合成「市場核心敘事（Market Narrative）」，不依賴 AI 即可生成盤前摘要
7. 使用 AI 將冰冷數據轉為白話文市場解說與今日操作策略一句話
8. 透過 Session State 快取最後一次**核心指標完整**的有效數據，保障系統在網路波動時平滑降級

### 技術架構要求

- **界面框架**：Streamlit
- **數據來源**：yfinance（指數/ETF/商品/個股）、FRED API（美債殖利率 DGS10）、Binance API（BTC）
- **AI 模型**：OpenAI（gpt-4o-mini）或 Google Gemini（gemini-1.5-flash）
- **視覺化工具**：Plotly Graph Objects
- **數據處理**：Pandas、NumPy
- **HTTP 請求**：requests
- **日期處理**：datetime、pytz
- **部署方式**：本地 `streamlit run` 執行；未來可部署於 GCP Cloud Run

### ⚡ V1.2 技術架構亮點

- **`price_data` 字典架構**：所有 yfinance 標的的完整 OHLCV DataFrame 儲存於 `price_data: dict[str, pd.DataFrame]`，為每次按鈕觸發的區域變數，供計算使用後不寫入 session state（避免記憶體膨脹）
- **`st.session_state` 快取**：僅儲存計算後的統計結果字典（非原始 DataFrame），且只在 SPY / QQQ / VIX 三項核心指標均有效時更新，防止部分失敗污染快取
- **Narrative 模板引擎**：由規則引擎而非 AI 合成 50–100 字市場敘事，零 API 費用，所有數值均有 None 型別保護
- **`DATA_PERIODS` 集中配置**：統一管理數據抓取期間，未來新增長期指標只需修改此配置
- **`NO_VOLUME_SYMBOLS` 白名單**：修正 VIX / DXY 等指數類標的的 Volume 過濾致命問題

---

## ⚙️ 全域配置常數（程式頂部定義）

```python
# ============================================================
# 全域配置（所有可調參數集中於此，修改指標時只改這裡）
# ============================================================

# 數據抓取期間
DATA_PERIODS = {
    "default": "2mo",    # 一般指標（MA20、支撐壓力、20日高低）
    "long_term": "12mo", # 長期均線（Vegas Tunnel 用，未來啟用）
}

# 不應用 Volume > 0 過濾的指數類標的白名單
NO_VOLUME_SYMBOLS = {"^VIX", "DX-Y.NYB", "^GSPC", "^IXIC", "^DJI"}

# 判斷 Session State 是否更新快取的核心指標
CACHE_GUARD_SYMBOLS = ["SPY", "QQQ", "^VIX"]

# AI 失敗預設回傳
DEFAULT_AI_RESPONSE = "目前無法連線至 AI 獲取解說，請依上方數據自行判斷。"

# 固定市場標的（板塊 ETF 用於資金輪動雷達）
SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLI", "XLV", "XLY"]
SECTOR_NAMES = {
    "XLK": "科技", "XLE": "能源", "XLF": "金融",
    "XLI": "工業", "XLV": "醫療", "XLY": "非必需消費"
}
CORE_MARKET_SYMBOLS = ["SPY", "QQQ", "SMH", "^VIX", "CL=F", "GC=F", "DX-Y.NYB"] + SECTOR_ETFS
```

---

## 🎯 功能需求規格

### F-001：用戶界面設計

**基本要求**：

- 頁面標題：`"🚦 專屬盤前戰情室 V1.2"`，使用彩虹色分隔線（`divider="rainbow"`）
- 左側控制區（sidebar）包含：
  - Logo 文字：`"📊 War Room Setup"`，彩虹色分隔線

  **AI Provider 選擇區**：
  ```python
  provider_choice = st.sidebar.selectbox(
      "🤖 AI Provider",
      options=["🔍 自動偵測（依 Key 前綴）", "OpenAI", "Google Gemini"],
      index=0
  )
  ```

  - 輸入 `ai_api_key`：`"請輸入 OpenAI 或 Gemini API Key"`（`type="password"`）
  - 輸入 `fred_api_key`：`"請輸入 FRED API Key"`（`type="password"`）
  - 提示文字：`"💡 請先輸入 Key，再點擊更新按鈕"`
  - 分隔線
  - 觀察股清單輸入（`st.text_area`）：預設值為 `NVDA\nTSM\nAMD\nGOOG\nPLTR`，說明文字「每行輸入一個股票代號」
  - 分隔線

  **快取狀態顯示**：
  ```python
  if "last_updated" in st.session_state:
      st.sidebar.caption(f"🕐 快取更新：{st.session_state['last_updated']}")
      st.sidebar.caption("（核心指標完整時自動保存）")
  ```

  - 免責聲明（見 F-009）

- 主頁面執行按鈕：`"🔄 獲取最新盤前戰報"`（`use_container_width=True`）

---

### F-002：數據獲取功能

**功能目標**：一鍵抓取所有市場數據，不需要使用者手動輸入任何股票代號（除觀察股外）。

**固定抓取清單**：

| 類別 | Symbol | 說明 |
|------|--------|------|
| 大盤 | SPY | S&P 500 ETF |
| 大盤 | QQQ | NASDAQ 100 ETF |
| 半導體 | SMH | 半導體 ETF |
| 恐慌 | ^VIX | VIX 恐慌指數 |
| 商品 | CL=F | WTI 原油期貨 |
| 商品 | GC=F | 黃金期貨 |
| 外匯 | DX-Y.NYB | 美元指數 DXY |
| 板塊 | XLK | 科技 |
| 板塊 | XLE | 能源 |
| 板塊 | XLF | 金融 |
| 板塊 | XLI | 工業 |
| 板塊 | XLV | 醫療 |
| 板塊 | XLY | 非必需消費 |

**【V1.2 修正】yfinance 數據抓取標準程序**：

```python
def fetch_price_data(symbol: str, period: str = DATA_PERIODS["default"]) -> pd.DataFrame | None:
    """
    標準化 yfinance 抓取。
    修正：指數類標的（VIX、DXY 等）不進行 Volume > 0 過濾，
    因其 Volume 欄位恆為 0 或不可靠，過濾會清空所有數據。
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d")
        # 第一步：清除 Close 為 NaN 的空 K 棒
        df = df.dropna(subset=["Close"])
        # 第二步：僅對有實際成交量的標的過濾 Volume > 0
        # 指數類（^VIX、DX-Y.NYB 等）在白名單中，跳過 Volume 過濾
        if symbol not in NO_VOLUME_SYMBOLS:
            df = df[df["Volume"] > 0]
        # 最少需要 2 筆才能計算漲跌幅
        if len(df) < 2:
            return None
        return df
    except Exception:
        return None
```

**【V1.2 修正】FRED API 殖利率抓取（limit 升至 10 覆蓋長假）**：

```python
def fetch_fred_us10y(fred_api_key: str) -> float | str:
    """
    抓取 FRED DGS10。limit=10 覆蓋最長連假（感恩節週、年末）。
    跳過值為 "." 或空字串的無效紀錄。
    """
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=DGS10&sort_order=desc&limit=10"
            f"&api_key={fred_api_key}&file_type=json"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        observations = resp.json()["observations"]
        for obs in observations:
            val = obs.get("value", ".")
            if val not in [".", "", None]:
                return float(val)
        return "無法取得"
    except Exception:
        return "無法取得"
```

**BTC**：使用 Binance API 抓取，端點為：
`https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT`
取 `lastPrice`（現價）與 `priceChangePercent`（24H 漲跌幅）

**觀察股**：根據使用者 sidebar 輸入的清單，使用 yfinance 逐一抓取

**`price_data` 字典架構（區域變數，不寫入 session state）**：

```python
# price_data 為每次按鈕觸發的函數區域變數
# 存放完整 OHLCV 供計算使用，計算完成後不持久化（避免 session state 記憶體膨脹）
# 未來新增 Vegas Tunnel（需 12mo）時，對指定標的改用 DATA_PERIODS["long_term"]
price_data: dict[str, pd.DataFrame] = {}

ALL_SYMBOLS = CORE_MARKET_SYMBOLS + watchlist_symbols  # watchlist 由 sidebar 輸入

for symbol in ALL_SYMBOLS:
    df = fetch_price_data(symbol)
    if df is not None:
        price_data[symbol] = df
```

---

### F-003：數據處理與計算

**計算項目 1：單日漲跌幅（V1.2 加除以零保護）**

```python
def calc_pct_change(df: pd.DataFrame) -> float | None:
    """
    取最後兩個有效收盤日計算漲跌幅。
    修正：加入 len 檢查與除以零保護，對特殊標的（warrants、新上市股）更穩定。
    """
    closes = df["Close"].tail(2).values
    if len(closes) < 2:
        return None
    prev_close = closes[-2]
    if prev_close == 0 or pd.isna(prev_close):
        return None
    return (closes[-1] - prev_close) / prev_close * 100
```

**計算項目 2：Market Regime 判定（固定規則，V1.2 第 1 層加 VIX 絕對值保底）**

依以下優先順序依序判斷，符合**任一層條件**即停止：

| 優先順序 | 狀態 | 觸發條件 | 設計理由 |
|---------|------|---------|---------| 
| 1 | 🔴 Risk-Off（極端恐慌）| (VIX 日漲幅 > 15% **且** QQQ 日跌幅 > 2%) **或** VIX 絕對值 > 30 | 前者捕捉崩盤速度，後者為 VIX 高位時的保底條件，防止「高 VIX 緩跌日」落入 Range |
| 2 | ⚠️ Liquidity Contraction（流動性收縮）| US10Y > 4.0% **且** VIX > 20 **且** 原油日漲幅 > 0% | 三重壓力同時出現，優先於一般 Risk-Off |
| 3 | 🟠 High Vol Risk-Off（高波動風險趨避）| VIX > 25 **且** QQQ 下跌 | 次級 Risk-Off（無流動性收縮特徵）|
| 4 | 🟢 Risk-On（風險偏好）| SPY > 0% **且** QQQ > 0% **且** VIX 下跌 | |
| 5 | 🟡 Range Market（震盪盤整）| 以上皆不符合 | 預設狀態 |

```python
def determine_market_regime(
    vix_pct: float | None,
    vix_val: float | None,
    qqq_pct: float | None,
    spy_pct: float | None,
    us10y_val: float | str,
    oil_pct: float | None,
) -> str:
    """固定規則判定 Market Regime，任何單一數值為 None 時該層條件視為不觸發。"""
    
    def safe(val, default=0.0):
        return val if isinstance(val, (int, float)) else default
    
    v_pct = safe(vix_pct)
    v_val = safe(vix_val)
    q_pct = safe(qqq_pct)
    s_pct = safe(spy_pct)
    o_pct = safe(oil_pct)
    us10y = safe(us10y_val, default=0.0)

    # 第 1 層：極端恐慌（速度條件 OR 絕對值條件）
    if (v_pct > 15 and q_pct < -2) or (v_val > 30):
        return "Risk-Off"

    # 第 2 層：流動性收縮
    if us10y > 4.0 and v_val > 20 and o_pct > 0:
        return "Liquidity Contraction"

    # 第 3 層：高波動 Risk-Off
    if v_val > 25 and q_pct < 0:
        return "High Volatility Risk-Off"

    # 第 4 層：Risk-On
    if s_pct > 0 and q_pct > 0 and v_pct < 0:
        return "Risk-On"

    # 第 5 層：震盪
    return "Range Market"
```

> **V1.2 新增說明**：第 1 層加入 `vix_val > 30` 保底條件，防止「VIX 緩慢爬升至 30+ 但單日漲幅未超過 15%」的高位恐慌場景被誤判為 Range Market。

**計算項目 3：情緒洗盤 vs 結構風險判定（固定規則）**

```python
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
```

**計算項目 4：板塊強弱排序**

將 XLK、XLE、XLF、XLI、XLV、XLY 的單日漲跌幅由高到低排序，
取最強板塊（第一名）與最弱板塊（最後一名）

**計算項目 5：觀察股狀態（含支撐/壓力）**

```python
def calc_watchlist_stats(df: pd.DataFrame) -> dict | None:
    """計算觀察股均線、支撐壓力統計，任何欄位計算失敗均回傳 None。"""
    try:
        latest_close = df["Close"].iloc[-1]
        ma20 = df["Close"].rolling(20).mean().iloc[-1]
        ma20_pct = (latest_close - ma20) / ma20 * 100 if ma20 != 0 else None

        # 短期支撐（近 20 日最低）
        support = df["Low"].rolling(20).min().iloc[-1]
        dist_support_pct = (latest_close - support) / support * 100 if support != 0 else None

        # 短期壓力（近 20 日最高）
        resistance = df["High"].rolling(20).max().iloc[-1]
        dist_resistance_pct = (latest_close - resistance) / resistance * 100 if resistance != 0 else None

        # 狀態標籤（基於距 MA20 百分比）
        if ma20_pct is not None:
            if ma20_pct > 3: status = "📈 偏強"
            elif ma20_pct < -3: status = "📉 偏弱"
            else: status = "➡️ 中性"
        else:
            status = "N/A"

        return {
            "現價": round(latest_close, 2),
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
```

**計算項目 6：Market Narrative 規則模板合成（V1.2 全面 None 保護）**

```python
def generate_narrative(
    regime: str,
    best_sector: str,
    worst_sector: str,
    us10y_val: float | str,
    oil_pct: float | None,
    vix_val: float | None,
) -> str:
    """
    規則模板 Narrative 引擎，零 AI 費用，零延遲。
    V1.2：所有數值均有 None 型別保護，不拋出 TypeError。
    """
    regime_text = {
        "Risk-Off": "市場處於恐慌性拋售狀態，多數風險資產同步下跌",
        "Liquidity Contraction": "債市、油市與波動率三重走升，市場進入流動性收縮環境",
        "High Volatility Risk-Off": "市場波動率偏高，風險資產面臨賣壓，但尚未達到極端恐慌",
        "Risk-On": "市場情緒轉樂觀，風險資產普遍走強",
        "Range Market": "市場方向尚不明確，各項指標呈震盪格局，觀望為宜",
    }.get(regime, "市場狀態不明")

    # None 保護：所有數值格式化加 isinstance 檢查
    rate_text = f"美債殖利率報 {us10y_val:.2f}%，" if isinstance(us10y_val, float) else ""
    oil_display = f"{abs(oil_pct):.1f}%" if isinstance(oil_pct, (int, float)) else "N/A"
    oil_dir = "走升" if isinstance(oil_pct, (int, float)) and oil_pct > 0 else "走低"
    oil_text = f"原油{oil_dir} {oil_display}，" if oil_pct is not None else ""

    action_advice = "謹慎觀望、輕倉為主" if regime in ["Risk-Off", "Liquidity Contraction"] else "順勢操作、嚴設停損"

    return (
        f"{regime_text}。{rate_text}{oil_text}"
        f"{best_sector} 板塊表現相對強勢，{worst_sector} 板塊承壓。"
        f"今日操作建議以{action_advice}為原則。"
    )
```

---

### F-004：主要顯示區域設計

使用 `st.tabs()` 建立以下四個頁籤：

**Tab 1：🌡️ 市場戰情總覽**

- 頂部用 `st.markdown` 以大字顯示 Market Regime 判定結果（含 emoji 燈號）
- 四欄 `st.metric()` 依序顯示：SPY、QQQ、SMH、VIX（含 delta 漲跌幅）
- 第二行四欄顯示：WTI 原油、黃金、DXY、BTC（含 delta）
- US10Y 單獨以 `st.metric()` 顯示，標示「10年期美債殖利率」
- **Market Narrative 摘要**，用 `st.info()` 顯示規則模板合成的敘事摘要（在 AI 解說上方）
- AI 白話文解說與今日策略（見 F-006）顯示於下方，用藍色 `st.info()` 框呈現

**Tab 2：🔍 結構分析**

- 情緒洗盤 vs 結構風險判定結果，以顯眼顏色框（`st.success` / `st.warning` / `st.error`）呈現

- **邏輯解說段落（50–120 字）**，由規則引擎根據觸發條件合成：

  ```python
  def generate_structural_explanation(risk_type: str, vix_val, us10y_val, oil_pct, spy_pct) -> str:
      """根據觸發的判定結果，生成對應的中文解說段落。"""
      explanations = {
          "⚠️ 結構性壓力升高": (
              f"VIX 升至 {vix_val:.1f}，同時美債殖利率維持高位（{us10y_val:.2f}%），"
              f"原油亦走升 {oil_pct:.1f}%。三項壓力指標同步走升，"
              "代表市場不只是技術性回檔，而是在重新定價通膨與流動性風險。建議今日以觀察為主，不追高。"
          ),
          "🌊 事件型波動": (
              f"VIX 單日暴漲，顯示市場發生突發性事件驅動的急速拋售。"
              "此類波動通常較短暫，但方向不明，建議靜待市場消化消息後再行動。"
          ),
          "💧 情緒性洗盤": (
              f"VIX 雖有上升，但美債殖利率未同步走升，SPY 仍維持在均線上方。"
              "這是典型的情緒性洗盤特徵，基本面未受威脅，跌幅可能有限。可適度關注買點。"
          ),
          "🟡 中性觀察": "各項壓力指標未出現明顯異常，市場處於相對穩定狀態，維持正常倉位管理即可。",
      }
      # None 保護
      try:
          return explanations.get(risk_type, "無法生成結構解說，請參考上方數據。")
      except Exception:
          return "無法生成結構解說，請參考上方數據。"
  ```

- 下方用表格列出觸發此判定的條件：

```
| 判斷條件        | 數值    | 是否觸發 |
| VIX > 25       | 29.5    | ✅       |
| US10Y 上升     | +0.05%  | ✅       |
| 原油上升       | +2.1%   | ✅       |
```

**Tab 3：🔄 資金輪動雷達**

- 使用 Plotly 橫向長條圖（`go.Bar`，`orientation='h'`）
- 由高到低排列六大板塊 ETF 漲跌幅
- 上漲用綠色（`#26a69a`），下跌用紅色（`#ef5350`）
- 標示最強與最弱板塊（annotation 文字）

**Tab 4：🎯 觀察股雷達（含支撐/壓力，V1.2 加 None 欄位安全顯示）**

- 使用 `st.dataframe()` 顯示以下欄位：

```
| 股票代號 | 現價 | 日漲跌(%) | MA20 | 距MA20(%) | 支撐位 | 距支撐(%) | 壓力位 | 距壓力(%) | 狀態 |
```

- 任何欄位計算失敗顯示 `"N/A"`，不影響其他行
- 「狀態」欄用顏色標示：📈 偏強 = 綠色，📉 偏弱 = 紅色，➡️ 中性 = 灰色
- 底部新增可展開的原始數據區塊（偵錯用）

---

### F-005：基本資訊展示

使用 `st.columns(4)` 展示核心指標，位置在 Tab 1 頂部。

每個 metric 格式：
```python
st.metric(label="SPY", value="$595.20", delta="-1.30%")
```

Delta 顏色規則：正值自動顯示綠色，負值自動顯示紅色（Streamlit 預設行為）。

VIX 的 delta 方向邏輯相反（VIX 上漲代表市場惡化），在 label 旁加標注：`"VIX ↑ = 市場壓力增加"`

---

### F-006：AI 分析功能

**分析目標**：將結構化數據轉為 100 字以內、新手可讀的盤前白話解說與一句話策略。

**AI Provider 判斷邏輯**：

```python
def resolve_ai_provider(api_key: str, user_selection: str) -> str:
    """
    依 sidebar 選擇決定 Provider。
    若選擇「自動偵測」，則根據 Key 前綴判斷。
    """
    if user_selection == "OpenAI":
        return "openai"
    elif user_selection == "Google Gemini":
        return "gemini"
    else:  # 自動偵測
        return "openai" if api_key.startswith("sk-") else "gemini"
```

**AI 角色設定（System Prompt）**：

```
你是一位冷靜、重風險控管的美股波段交易員，擅長用最簡單的語言解釋市場。
你服務的對象是剛入市的小資族新手，因此你的語言必須：
- 避免專業術語（若使用必須立刻用括號解釋）
- 不誇大、不預測未來
- 強調風險控管，在 Risk-Off 環境下主動建議「多看少做」
- 說明「為什麼」資金在移動，不只說「資金從A流向B」
```

**完整 User Prompt**（程式中動態填入數據）：

```
請基於以下昨日美股收盤數據，用繁體中文撰寫：
1. 一段「盤前白話解說」（100字以內，解釋今天市場在演什麼、為什麼）
2. 一句「今日操作策略」（20字以內，具備防呆性質）

數據如下：
- SPY 漲跌：{spy_pct}%
- QQQ 漲跌：{qqq_pct}%
- VIX 數值：{vix_val}（日漲跌 {vix_pct}%）
- 10年期美債殖利率：{us10y_val}%
- WTI 原油漲跌：{oil_pct}%
- 系統判定 Market Regime：{market_regime}
- 情緒洗盤 vs 結構風險判定：{risk_type}
- 最強板塊：{best_sector}（{best_pct}%）
- 最弱板塊：{worst_sector}（{worst_pct}%）

輸出格式（請嚴格遵守，不要加任何 Markdown 標題）：
[盤前解說]：...
[今日策略]：...
```

**注意**：若 API Key 未輸入，此區塊改顯示 `st.warning("請輸入 API Key 以啟用 AI 解說功能")`，但其他數據仍正常顯示。

---

### F-007：輔助功能與程式入口結構（V1.2 明確化渲染流程）

**核心原則**：頁面永遠有東西可看，不因未點擊按鈕或數據抓取失敗而顯示空白。

**程式入口結構（必須嚴格遵守）**：

```python
# ============================================================
# 【程式入口結構】
# ============================================================

# --- 區塊 A：按鈕之外（頁面每次載入都執行）---
# 顯示快取橫幅或引導提示
if "market_data" in st.session_state:
    st.info(
        f"📌 顯示最後一次完整戰報（更新於 {st.session_state['last_updated']}）。"
        "點擊按鈕可刷新數據。"
    )
    _render_all_tabs(st.session_state["market_data"])  # 渲染舊數據
else:
    st.markdown(
        "### 👋 歡迎使用盤前戰情室\n"
        "請在左側輸入 API Key，再點擊「🔄 獲取最新盤前戰報」開始分析。"
    )

# --- 區塊 B：按鈕被點擊時執行 ---
if st.button("🔄 獲取最新盤前戰報", use_container_width=True):
    with st.spinner("⏳ 聯網抓取市場數據與 AI 分析中，請稍候..."):
        
        # 執行所有數據抓取（每個呼叫獨立隔離）
        market_data = _fetch_all_data(...)   # 回傳統計結果字典
        
        # 【V1.2 快取守衛】：核心指標有效才更新 session state
        if all(market_data.get(sym) is not None for sym in CACHE_GUARD_SYMBOLS):
            st.session_state["market_data"] = market_data
            st.session_state["last_updated"] = (
                datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
            )
            st.success("✅ 戰報生成完畢！數據已快取。")
        else:
            st.warning("⚠️ 本次核心數據抓取不完整，未更新快取。上方顯示上次有效數據。")
        
        # 渲染最新數據（即使未更新快取，也渲染本次抓取到的部分數據）
        _render_all_tabs(market_data)
```

**說明**：
- `_fetch_all_data()` 負責所有外部呼叫，回傳純數字/字串的統計結果字典（**不含** DataFrame）
- `price_data` DataFrame 字典為 `_fetch_all_data()` 的內部區域變數，用完即釋放
- `_render_all_tabs(data)` 負責渲染四個 Tab，接受統計結果字典作為輸入

在 Tab 4 底部新增可展開的原始數據區塊：

```python
with st.expander("📄 查看原始數據（偵錯用）"):
    st.dataframe(raw_data_df)
```

---

### F-008：錯誤處理與用戶體驗（V1.2 全面強化版）

**核心原則**：任何單一數據源失敗，不得導致整個頁面白屏（White Screen of Death）。

**隔離式 Try-Except 架構**：

```python
# 每個標的獨立隔離，互不影響
pct_changes: dict[str, float | None] = {}
for symbol in ALL_SYMBOLS:
    try:
        df = fetch_price_data(symbol)
        if df is not None:
            price_data[symbol] = df
            pct_changes[symbol] = calc_pct_change(df)
        else:
            pct_changes[symbol] = None
    except Exception:
        pct_changes[symbol] = None

# FRED 獨立隔離
try:
    us10y_val = fetch_fred_us10y(fred_api_key)
except Exception:
    us10y_val = "無法取得"

# Binance 獨立隔離
try:
    btc_data = fetch_binance_btc()
except Exception:
    btc_data = {"price": "N/A", "pct": "N/A"}

# Narrative 引擎獨立隔離（規則模板，理論上不應失敗，但仍保護）
try:
    narrative = generate_narrative(regime, best_sector, worst_sector, us10y_val, oil_pct, vix_val)
except Exception:
    narrative = "市場敘事生成失敗，請參考上方指標數據。"

# AI 獨立隔離
try:
    ai_response = call_ai(api_key, provider, prompt)
    if not ai_response or not ai_response.strip():
        ai_response = DEFAULT_AI_RESPONSE
except Exception:
    ai_response = DEFAULT_AI_RESPONSE
```

**完整錯誤處理對照表**：

| 錯誤情境 | 顯示處理 | 是否繼續執行 |
|---------|---------|------------|
| 未輸入 API Key 就點擊按鈕 | `st.warning("⚠️ 請先於左側輸入必要的 API Key。")` 並停止 | ❌ |
| yfinance 個別標的失敗 | 該欄位填入 `"N/A"`，Metric 顯示 N/A | ✅ |
| VIX / DXY 等指數 Volume=0 | 由 `NO_VOLUME_SYMBOLS` 白名單跳過 Volume 過濾，正常抓取 | ✅ |
| FRED API 失敗 | US10Y 顯示 `"無法取得"` | ✅ |
| FRED 所有紀錄均為空值 | 以 `limit=10` 覆蓋，仍無效則顯示 `"無法取得"` | ✅ |
| Binance API 失敗 | BTC 顯示 `"無法取得"` | ✅ |
| AI API 失敗 / 回傳空值 | 顯示 `DEFAULT_AI_RESPONSE` | ✅ |
| 核心指標（SPY/QQQ/VIX）不完整 | 不更新 session state，顯示警告，仍渲染本次部分數據 | ✅ |
| 全部抓取失敗 | session state 有歷史數據則顯示舊數據 + 警告橫幅 | ✅ |

---

### F-009：免責聲明與安全

**位置**：sidebar 底部（`st.sidebar.markdown`）

```markdown
---
### 📢 免責聲明
本系統僅為個人盤前資訊整理工具。
AI 解說**不構成任何投資建議**。
所有交易決策請自行判斷，嚴格控管風險。
```

**安全要求**：
- 所有 API Key 使用 `type="password"` 輸入
- 不在程式碼任何位置 hardcode API Key

---

## 🎨 界面設計標準

- **整體風格**：專業金融儀表板，深色主題（Streamlit dark mode 相容）
- **色彩規範**：上漲 `#26a69a`（綠）、下跌 `#ef5350`（紅）、中性 `#78909c`（灰）、警示 `#FFA726`（橙）
- **圖表工具**：統一使用 Plotly Graph Objects，所有圖表加 `use_container_width=True`
- **版面**：避免過度擁擠；各 Tab 內容用 `st.divider()` 適當分隔

---

## 📊 品質標準

- 初始載入：3 秒內完成
- 數據抓取 + AI 分析：15 秒內完成
- 相容瀏覽器：Chrome / Firefox / Safari
- 單一數據源失敗不影響其他板塊渲染（100% 隔離）
- 頁面任何狀態均有內容可顯示（快取降級保障）

---

## 🔮 架構擴充性預留

本 V1.2 架構已預留以下擴充能力：

| 未來功能 | 所需數據 | 已預留 |
|---------|---------|-------|
| SNR 支撐壓力位自動判定 | OHLCV High/Low | ✅ `price_data[symbol]["High"/"Low"]` |
| Vegas Tunnel 均線通道 | 長期 Close | ✅ `DATA_PERIODS["long_term"]` 切換即用 |
| ATR 真實波幅指標 | OHLC | ✅ `price_data[symbol]` |
| 成交量異常偵測 | Volume | ✅ `price_data[symbol]["Volume"]` |
| 多時框架分析 | 需新增 interval 參數 | 需擴充 `fetch_price_data` |

---

## 🤖 AI 實作指令

**請根據以上完整規格說明書，生成一個完整可運行的 Streamlit Python 應用程式。**

### 必要實現要求

1. 完全實現 F-001 到 F-009 所有功能
2. 符合界面設計標準（專業、易用、美觀）
3. Market Regime 與情緒/結構判定**必須使用規格中定義的固定規則**，不可由 AI 臆測
4. AI 分析功能只負責生成白話文，判斷邏輯由程式負責
5. Market Narrative 由規則模板引擎生成，不得由 AI 即時呼叫
6. 所有外部呼叫必須獨立 try-except 隔離
7. 程式結構**必須遵守 F-007 定義的入口結構**（按鈕外渲染快取 / 按鈕內更新數據）

### 技術實現要求（V1.2 完整清單）

- 框架：Streamlit
- **`^VIX`、`DX-Y.NYB` 等指數類標的必須跳過 `Volume > 0` 過濾（使用 `NO_VOLUME_SYMBOLS` 白名單）**
- **所有 yfinance 呼叫必須先 `.dropna(subset=["Close"])` + 條件性 `Volume > 0` 過濾後，取最後兩個有效交易日計算漲跌幅**
- **`calc_pct_change` 必須有 len 檢查與除以零保護**
- **FRED API 必須使用 `limit=10`，並用迴圈跳過 `"."` 或空值**
- **Market Regime 第 1 層必須包含 `or vix_val > 30` 的絕對值保底條件**
- **Session State 只存計算結果字典（非原始 DataFrame），且只在 CACHE_GUARD_SYMBOLS 均有效時更新**
- AI 呼叫支援 OpenAI 與 Gemini 兩種，根據 sidebar 選擇或 Key 前綴自動判斷
- AI 失敗時回傳 `DEFAULT_AI_RESPONSE`
- 使用 `DATA_PERIODS` 字典集中管理抓取期間
- 程式碼需有清楚的繁體中文註釋
- 避免使用已棄用的 yfinance API（使用 `.history()` 取代 `.download()`）

### 交付物要求

**一個 Python 檔案**：`premarket_warroom_v1_2.py`

可直接執行：
```bash
pip install streamlit yfinance plotly pandas numpy requests openai google-generativeai
streamlit run premarket_warroom_v1_2.py
```

---

## 📝 V1.1 → V1.2 變更紀錄

| 問題 ID | 功能區塊 | V1.1 問題 | V1.2 修正 |
|--------|---------|----------|---------|
| G1-A | F-002 | VIX / DXY 的 `Volume > 0` 過濾清空所有 K 棒（致命）| `NO_VOLUME_SYMBOLS` 白名單，指數類跳過 Volume 過濾 |
| G1-B | F-002 | FRED `limit=5` 在長假時不足 | 升至 `limit=10` |
| G1-C | F-003 | Narrative 引擎未處理 `oil_pct=None` | 所有數值加 `isinstance` None 保護 |
| P2-A | F-003 | Regime 第 1 層 QQQ=-1.9% 時可能誤判 Range | 加 `or vix_val > 30` 保底條件 |
| P2-B | F-007 | 部分成功時仍覆蓋快取，引入污染數據 | Session State 寫入守衛：核心指標均有效才更新 |
| P2-C | F-003 | `calc_pct_change` 未防除以零 | 加 `len` 與 `prev_close == 0` 檢查 |
| C3-A | F-007 | session_state 存原始 DataFrame，未來記憶體膨脹風險 | 明確規範只存計算結果字典，DF 為區域變數 |
| C3-B | F-007 | 快取降級渲染邏輯位置未明確，有白屏風險 | 明確定義程式入口結構（按鈕外 vs 按鈕內）|
| C3-C | 全域 | 抓取期間分散管理，未來指標難以擴充 | 新增 `DATA_PERIODS` 全域集中配置 |

---

*規格書版本：V1.2 | 適合對象：美股波段交易新手 | 系統定位：盤前決策輔助，非自動交易*
*三方審議：Gemini 3.1 Pro × GPT-OSS 120B × Claude Sonnet 4.6 | 生成日期：2026-03-08*

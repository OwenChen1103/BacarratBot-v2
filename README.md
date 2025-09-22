# 百家樂自動投注機器人 (AutoBet Bot)

🎯 **一個以 UI 偵測驅動的百家樂自動投注機器人，支援乾跑模式，獨立運作，不依賴外部監控程式。**

## 🌟 主要特性

- **🛡️ 安全優先**: 預設乾跑模式，不會真實下注
- **🎯 精準定位**: 基於螢幕 UI 偵測，精確點擊籌碼與投注區
- **📊 策略豐富**: 支援固定、馬丁格爾、反馬丁格爾等多種策略
- **🔒 風控完善**: 止損止盈、單局上限、冪等鎖保護
- **📝 完整日誌**: 詳細會話記錄與審計追蹤
- **🔧 易於配置**: JSON/YAML 配置檔案，支援多種事件來源

## 🏗️ 專案架構

```
autobet-bot/
├── README.md                    # 本檔案
├── requirements.txt             # Python 依賴套件
├── .env.example                 # 環境變數範例
│
├── configs/                     # 配置檔案
│   ├── strategy.default.json    # 預設策略配置
│   ├── positions.sample.json    # 位置配置範例
│   └── ui.yaml                   # UI 偵測設定
│
├── data/                        # 資料目錄
│   ├── logs/                    # 旋轉日誌
│   ├── sessions/                # 會話記錄 (CSV/NDJSON)
│   └── screenshots/             # 關鍵截圖
│
├── templates/                   # 模板圖片
│   ├── chips/                   # 籌碼模板
│   ├── bets/                    # 下注區域模板
│   └── controls/                # 控制按鈕模板
│
├── scripts/                     # 輔助工具
│   ├── capture_positions.py     # 位置捕獲工具
│   ├── check_templates.py       # 模板品質檢查
│   └── replay_events.py         # 事件回放工具
│
├── src/autobet/                 # 核心模組
│   ├── run_bot.py               # 主入口程式
│   ├── autobet_engine.py        # 狀態機引擎
│   ├── actuator.py              # 滑鼠操作模組
│   ├── positions.py             # 位置管理
│   ├── strategy.py              # 策略管理
│   ├── planner.py               # 下注計劃器
│   ├── detectors.py             # UI 偵測器
│   ├── io_events.py             # 事件來源管理
│   └── risk.py                  # 風控管理
│
└── tests/                       # 測試檔案
    └── test_dryrun.py           # 乾跑測試
```

## 🚀 快速開始

### 1. 環境準備

**系統需求:**
- Python 3.8+
- Windows 10/11
- 1920x1080 螢幕解析度（建議）

**安裝依賴:**
```bash
# 建立虛擬環境
python -m venv .venv
.venv\\Scripts\\activate

# 安裝依賴套件
pip install -r requirements.txt
```

### 2. 環境配置

```bash
# 複製環境變數範例
copy .env.example .env

# 編輯 .env 檔案，調整必要設定
# DRY_RUN=1          # 1=乾跑模式, 0=實戰模式
# SCREEN_DPI_SCALE=1.0  # 螢幕縮放係數
```

### 3. 位置校準

**步驟 1: 捕獲位置**
```bash
python scripts/capture_positions.py
```
- 按照提示依序雙擊各個遊戲元素
- 生成 `positions.json` 位置配置檔案

**步驟 2: 檢查模板品質**
```bash
python scripts/check_templates.py
```
- 驗證模板匹配品質
- 確保 NCC 分數 > 0.8

### 4. 乾跑測試

```bash
# 執行完整乾跑測試
python tests/test_dryrun.py

# 或直接啟動機器人（乾跑模式）
python -m src.autobet.run_bot --dry-run
```

### 5. 實戰部署

**⚠️ 僅在乾跑測試完全穩定後進行！**

```bash
# 修改 .env 檔案
# DRY_RUN=0

# 或使用命令行啟動實戰模式
python -m src.autobet.run_bot --strategy configs/strategy.default.json
```

## ⚙️ 配置說明

### 策略配置 (strategy.json)

```json
{
  "unit": 1000,                          # 基本單位金額
  "targets": ["banker"],                  # 下注目標
  "split_units": {"banker": 1},           # 單位分配
  "staking": {
    "type": "martingale",                 # 遞增類型
    "base_units": 1,                      # 基礎單位
    "max_steps": 3,                       # 最大步驟
    "reset_on_win": true                  # 勝利時重置
  },
  "limits": {
    "per_round_cap": 10000,              # 單局上限
    "session_stop_loss": -20000,         # 會話止損
    "session_take_profit": 30000         # 會話止盈
  }
}
```

### UI 偵測配置 (ui.yaml)

```yaml
overlay:
  roi: [1450, 360, 420, 50]             # 下注期狀態條區域
  method: "gray_mean"                    # 偵測方法
  gray_open_lt: 120.0                    # 灰階門檻

click:
  jitter_px: 2                           # 點擊抖動範圍
  move_delay_ms: [40, 120]               # 移動延遲範圍
  click_delay_ms: [40, 80]               # 點擊延遲範圍
```

## 🎮 遊戲元素對應

### 可點擊目標

**籌碼:** `chip_100`, `chip_1k`, `chip_5k`, `chip_10k`, `chip_50k`

**主注:** `player`(閒), `banker`(莊), `tie`(和)

**副注:** `p_pair`(閒對), `b_pair`(莊對), `lucky6`(幸運6)

**控制:** `confirm`(確定), `cancel`(取消)

### 狀態偵測

**下注期判斷:** 透過上方紫色橫條 (overlay) 的灰階平均值或 NCC 模板匹配判斷是否可下注

## 🔧 進階功能

### 事件來源模式

**A. SSE 模式** - 訂閱 Reader 的 SSE 事件流
```bash
# .env 設定
EVENT_SOURCE_MODE=sse
READER_SSE_URL=http://127.0.0.1:8888/events
```

**B. NDJSON 回放** - 播放歷史事件檔案
```bash
# .env 設定
EVENT_SOURCE_MODE=ndjson
NDJSON_REPLAY_FILE=data/sessions/events.ndjson
```

**C. Demo 模式** - 本地模擬事件（預設）
```bash
# .env 設定
EVENT_SOURCE_MODE=demo
DEMO_ROUND_INTERVAL_SEC=15
```

### 策略過濾器

支援根據歷史結果動態調整策略:

```json
{
  "filters": [
    {
      "name": "閒家勝出後下莊家",
      "when": "last_winner == 'P'",
      "override_targets": ["banker"],
      "override_units": {"banker": 2}
    }
  ]
}
```

### 風控機制

- **冪等鎖**: 防止同一輪次重複下注
- **送單保護**: 確認前最後檢查 overlay 狀態
- **環境監控**: 偵測螢幕變化自動暫停
- **緊急停止**: 立即切換乾跑模式

## 🧪 測試與驗證

### 單元測試

```bash
# 執行所有測試
python -m pytest tests/

# 執行特定測試
python tests/test_dryrun.py
```

### 手動驗證清單

- [ ] 位置捕獲完成，生成有效的 `positions.json`
- [ ] 模板檢查通過，NCC 分數 > 0.8
- [ ] 乾跑測試 30 局無錯誤
- [ ] 狀態機正常切換 (idle → betting_open → placing_bets)
- [ ] 所有點擊顯示 `[DRY] click` 訊息
- [ ] 會話記錄正常生成

### 實戰前檢查

- [ ] 小額測試（unit: 100）
- [ ] 嚴格限制（per_round_cap: 500）
- [ ] 監控 overlay 偵測準確性
- [ ] 確認點擊位置精確度

## 📊 監控與日誌

### 即時狀態

- **連接狀態**: 事件來源連接品質
- **狀態機**: 當前執行階段
- **下注計劃**: 金額分配與目標
- **會話統計**: 局數、損益、連勝負

### 日誌檔案

- **執行日誌**: `data/logs/autobet.log`
- **會話記錄**: `data/sessions/session-YYYYMMDD-HHMM.csv`
- **事件記錄**: `data/sessions/events.ndjson`

## 🛠️ 故障排除

### 常見問題

**Q: 模板匹配失敗**
```bash
# 重新檢查模板品質
python scripts/check_templates.py

# 重新捕獲位置
python scripts/capture_positions.py
```

**Q: overlay 偵測不準確**
```yaml
# 調整 ui.yaml 中的門檻值
overlay:
  gray_open_lt: 100.0  # 降低門檻值
```

**Q: 點擊位置偏移**
```bash
# 檢查 DPI 縮放設定
# .env 檔案中調整 SCREEN_DPI_SCALE
```

### 除錯模式

```bash
# 啟用詳細日誌
export LOG_LEVEL=DEBUG
python -m src.autobet.run_bot
```

## ⚠️ 重要提醒

1. **預設乾跑**: 所有操作預設為乾跑模式，確保安全
2. **測試優先**: 務必完成乾跑測試後再考慮實戰
3. **小額開始**: 實戰時從小額開始，逐步調整
4. **風控至上**: 設定合理的止損止盈，控制風險
5. **持續監控**: 實戰時需人工監控，避免意外

## 📞 技術支援

如遇問題請檢查：
1. 日誌輸出 (`data/logs/autobet.log`)
2. 位置配置是否正確
3. 模板品質是否達標
4. 環境變數設定

---

## 🚀 快速啟動指令

```bash
# 完整測試流程
python tests/test_dryrun.py

# 位置捕獲
python scripts/capture_positions.py

# 模板檢查
python scripts/check_templates.py

# 啟動機器人（乾跑）
python -m src.autobet.run_bot --dry-run

# 啟動機器人（實戰，需確認）
python -m src.autobet.run_bot
```

**🎯 準備就緒！開始您的自動投注之旅！**
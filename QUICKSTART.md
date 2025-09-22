# 百家樂自動下注機器人 - 快速上手指南

## 🎯 系統概述

本系統採用「Reader（監控）+ Bot（下注）」雙元架構：
- **Reader端**: 監控遊戲畫面、偵測元素位置、推播事件
- **Bot端**: 接收事件、執行策略、自動下注（支援乾跑模式）

## 📋 環境需求

- Python 3.10+
- Windows 10/11
- 依賴套件：`pip install PySide6 opencv-python numpy pyautogui requests flask`

## 🚀 快速開始

### 步驟 1: 校準與偵測

1. **縮放校準**（首次使用必須）
   ```bash
   python scale_calibration.py
   ```
   - 按照提示校準最佳縮放比例
   - 確保模板匹配準確

2. **元素偵測**（生成點位配置）
   ```bash
   python element_detection.py
   ```
   - 選擇遊戲截圖或使用即時截圖
   - 等待偵測完成，生成 `positions.json`

### 步驟 2: 乾跑測試

1. **執行測試腳本**
   ```bash
   python test_dry_run.py
   ```
   - 自動測試所有核心模組
   - 驗證通信和基本功能

2. **手動驗收**（雙視窗模式）

   **Terminal 1 - 啟動Reader**
   ```bash
   python ResultWindow.py
   ```
   - 點擊「📡 啟動推播」
   - 確認狀態顯示「推播中」
   - 可選：點擊「開始監控」進行完整測試

   **Terminal 2 - 啟動Bot**
   ```bash
   python -m bot.BotConsole
   ```
   - 點擊「🔗 連接Reader」
   - 確認SSE狀態為「✅ 已連接」
   - **勾選「🧪 乾跑模式」**（重要！）
   - 點擊「▶️ 啟動」

3. **驗收標準**
   - ✅ Reader與Bot成功連接
   - ✅ Bot狀態機正常運作（idle/betting_open等）
   - ✅ 模擬下注顯示 `[DRY] click` 訊息
   - ✅ 30秒內無錯誤或崩潰

### 步驟 3: 策略配置

1. **編輯策略**（Bot視窗內）
   - 調整「基本設定」：單位金額、下注目標
   - 設定「單位分配」：各目標的單位數
   - 選擇「遞增策略」：fixed（固定）或 martingale（倍投）
   - 配置「風控限制」：單局上限、止損/止盈

2. **策略示例**
   ```json
   {
     "unit": 1000,
     "targets": ["banker", "lucky6"],
     "split_units": {"banker": 3, "lucky6": 1},
     "staking": {
       "type": "martingale",
       "base_units": 1,
       "max_steps": 3,
       "reset_on_win": true
     },
     "limits": {
       "per_round_cap": 10000,
       "session_stop_loss": -20000,
       "session_take_profit": 30000,
       "max_retries": 1
     }
   }
   ```

## ⚙️ 核心架構

### Reader端組件
- `element_detection.py` - 元素偵測，生成 positions.json
- `single_table_monitor.py` - 畫面監控，識別輪次結果
- `ResultWindow.py` - Reader主視窗，事件推播
- `ipc/reader_events.py` - SSE事件推播服務

### Bot端組件
- `autobet/actuator.py` - 滑鼠操作，支援乾跑模式
- `autobet/autobet_engine.py` - 狀態機，策略執行
- `bot/BotConsole.py` - Bot控制視窗，SSE訂閱
- `configs/strategy.json` - 策略配置

### 通信協議
```json
{
  "type": "RESULT",
  "phase": "RESULT",
  "round_id": "19219058",
  "winner": "B",
  "table_id": "WG-137",
  "ts": 1695196498123
}
```

## 🔒 安全機制

### 乾跑模式（預設）
- 所有點擊操作顯示為 `[DRY] click <name> -> (x,y)`
- 不會真的移動滑鼠或點擊
- 策略邏輯正常執行，便於測試

### 風控機制
- **送單前檢查**: 最後一刻檢查overlay狀態
- **臨界保護**: 關窗時自動 `cancel()` 放棄下注
- **冪等處理**: 相同 round_id 絕不重押
- **緊急停止**: 立即停用並切回乾跑模式

### 限制保護
- 單局上限（per_round_cap）
- 會話止損/止盈（session_stop_loss/take_profit）
- 補點次數限制（max_retries）

## 🎮 實戰模式

**⚠️ 僅在乾跑測試完全穩定後進行！**

1. **小額測試**
   - 取消「🧪 乾跑模式」勾選
   - 調整策略為小額（unit: 100）
   - 設定嚴格限制（per_round_cap: 500）

2. **監控要點**
   - 觀察 Bot 狀態機切換
   - 確認點擊位置準確
   - 檢查臨界關窗處理

3. **異常處理**
   - 螢幕縮放變更 → Bot 自動暫停
   - 通信中斷 → Bot 重連前不出手
   - 環境異常 → 立即切換至 paused 狀態

## 📊 監控與日誌

### Bot Console 顯示
- **連接狀態**: SSE連接品質
- **狀態機**: stopped/idle/betting_open/placing_bets/wait_confirm/in_round
- **當前計畫**: 下注金額和目標
- **會話統計**: 局數、損益、連勝負
- **執行日誌**: 詳細操作記錄

### 審計追蹤
- CSV日誌：`data/results.csv`
- 包含：計畫、實際點擊、回讀驗證、送單、取消、結果
- 以 round_id 為主鍵，支援撤銷追蹤

## 🛠️ 故障排除

### 常見問題

1. **positions.json 不存在**
   - 執行 `python element_detection.py` 重新偵測

2. **SSE 連接失敗**
   - 確認 Reader 已啟動推播
   - 檢查防火牆設定（localhost:8888）

3. **模板匹配失敗**
   - 重新執行縮放校準
   - 檢查遊戲視窗解析度

4. **滑鼠點擊偏移**
   - 確認 DPI 設定
   - 重新執行元素偵測

### 調試模式
```python
# 在各模組開啟詳細日誌
logging.basicConfig(level=logging.DEBUG)
```

## 📁 檔案結構

```
AutomatedBettingRobot/
├── autobet/                    # Bot核心模組
│   ├── actuator.py            # 滑鼠操作
│   └── autobet_engine.py      # 狀態機引擎
├── bot/                       # Bot介面
│   └── BotConsole.py         # 控制視窗
├── ipc/                       # 通信模組
│   └── reader_events.py      # SSE推播
├── configs/                   # 配置文件
│   ├── strategy.json         # 策略配置
│   └── strategy.default.json # 預設策略
├── templates/                 # 模板圖片
├── data/                     # 資料目錄
│   └── results.csv          # 審計日誌
├── positions.json            # 元素位置（偵測生成）
├── element_detection.py     # 元素偵測工具
├── ResultWindow.py          # Reader主視窗
├── test_dry_run.py          # 乾跑測試
└── QUICKSTART.md           # 本文件
```

## 🚨 重要提醒

1. **預設乾跑**: 所有操作預設為乾跑模式，確保安全
2. **測試優先**: 務必完成乾跑測試後再考慮實戰
3. **小額開始**: 實戰時從小額開始，逐步調整
4. **風控至上**: 設定合理的止損止盈，控制風險
5. **持續監控**: 實戰時需人工監控，避免意外

---

🎯 **快速測試指令**
```bash
# 完整測試流程
python test_dry_run.py

# 啟動 Reader
python ResultWindow.py

# 啟動 Bot（新終端）
python -m bot.BotConsole
```

📞 **技術支援**: 如遇問題請檢查日誌輸出並參考故障排除章節。
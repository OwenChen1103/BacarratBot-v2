# 🎯 BacarratBot-v2 專案交接文件

**版本**: v2.0
**建立日期**: 2025-09-27
**交接日期**: 2025-09-27
**狀態**: 開發中（核心功能完成）

---

## 📋 目錄

1. [專案概覽](#專案概覽)
2. [架構設計](#架構設計)
3. [開發進度](#開發進度)
4. [技術棧與依賴](#技術棧與依賴)
5. [配置系統](#配置系統)
6. [UI 功能模組](#ui-功能模組)
7. [核心引擎系統](#核心引擎系統)
8. [偵測系統](#偵測系統)
9. [部署與使用](#部署與使用)
10. [已知問題與待辦](#已知問題與待辦)
11. [下階段路線圖](#下階段路線圖)

---

## 🌟 專案概覽

### 核心目標
百家樂自動投注機器人，基於螢幕 UI 偵測驅動，支援乾跑模式與多種投注策略。

### 主要特性
- **🛡️ 安全優先**: 預設乾跑模式，完整風控機制
- **🎯 精準定位**: OpenCV 模板匹配 + HSV 顏色偵測
- **📊 策略豐富**: 馬丁格爾、反馬丁格爾、固定投注
- **🔒 風控完善**: 止損止盈、冪等鎖、下注保護
- **📝 完整記錄**: CSV/NDJSON 會話記錄與審計
- **🎮 圖形介面**: PySide6 現代化 UI 管理介面

### 執行模式
- **命令行模式**: `python -m src.autobet.run_bot`
- **GUI 模式**: `python run_gui.py`

---

## 🏗️ 架構設計

### 專案結構
```
BacarratBot-v2/
├── configs/                    # 配置檔案
│   ├── strategy.json          # 策略配置（當前）
│   ├── strategy.default.json  # 預設策略模板
│   ├── positions.json         # 位置校準配置
│   └── positions.sample.json  # 位置配置範例
├── data/                       # 資料目錄
│   ├── logs/                  # 執行日誌
│   └── sessions/              # 會話記錄
├── src/autobet/               # 核心模組
│   ├── autobet_engine.py      # 主狀態機引擎
│   ├── detectors.py          # UI 偵測系統
│   ├── actuator.py           # 滑鼠操作模組
│   ├── planner.py            # 下注計劃器
│   ├── risk.py               # 風控管理
│   ├── io_events.py          # 事件來源管理
│   └── run_bot.py            # 命令行入口
├── ui/                        # GUI 介面
│   ├── main_window.py        # 主視窗
│   ├── pages/                # 功能頁面
│   └── workers/              # 背景工作執行緒
├── templates/                 # 模板圖片
├── scripts/                   # 輔助工具
└── tests/                     # 測試檔案
```

### 核心組件關係圖
```
GUI Layer:           main_window.py → pages/ → workers/
                           ↓
Engine Layer:        autobet_engine.py ← io_events.py
                           ↓
Detection Layer:     detectors.py → actuator.py
                           ↓
Config Layer:        strategy.json + positions.json
```

---

## ✅ 開發進度

### 已完成模組 (7/9)

#### ✅ 核心引擎 (autobet_engine.py)
- **狀態**: 完成
- **功能**: 完整狀態機實現 (idle → betting_open → placing_bets → wait_confirm → in_round → eval_result)
- **特色**: 多執行緒、事件驅動、風控整合

#### ✅ 偵測系統 (detectors.py)
- **狀態**: 完成（生產版本）
- **功能**:
  - `RobustOverlayDetector`: HSV 顏色閘控 + 多尺度字形匹配
  - `ProductionOverlayDetector`: 簡化版雙閾值連續幀檢測
  - `OverlayDetectorWrapper`: 向下相容包裝器
- **特色**: 滯後決策、抗閃爍、模板快取

#### ✅ 風控系統 (risk.py)
- **狀態**: 完成
- **功能**: 冪等鎖、限額檢查、會話保護

#### ✅ 操作系統 (actuator.py)
- **狀態**: 完成
- **功能**: 精確滑鼠控制、乾跑模式、點擊保護

#### ✅ 策略系統 (strategy.py + planner.py)
- **狀態**: 完成
- **功能**: 馬丁格爾策略、籌碼配置、下注計劃

#### ✅ GUI 架構 (ui/)
- **狀態**: 完成
- **功能**: 9 個功能頁面、工作執行緒、信號槽架構

#### ✅ 配置系統
- **狀態**: 完成
- **功能**: JSON 配置、環境變數、CLI 參數覆蓋

### 進行中模組 (2/9)

#### 🔄 位置校準頁面 (page_positions.py)
- **狀態**: 80% 完成
- **已實現**: 基本位置捕獲、ROI 設定
- **待完成**: 批量校準、驗證機制

#### 🔄 覆蓋層偵測頁面 (page_overlay.py)
- **狀態**: 85% 完成
- **已實現**: 生產版偵測器整合、即時預覽
- **待完成**: HSV 參數調整介面

---

## 🔧 技術棧與依賴

### 核心技術
- **Python**: 3.8+
- **GUI 框架**: PySide6 (Qt 6)
- **影像處理**: OpenCV (cv2)
- **數值計算**: NumPy
- **螢幕操作**: PyAutoGUI
- **配置**: JSON, YAML, python-dotenv

### 完整依賴清單 (requirements.txt)
```
PySide6>=6.0.0
opencv-python>=4.5.0
numpy>=1.20.0
pyautogui>=0.9.50
python-dotenv>=0.19.0
PyYAML>=6.0
```

### 開發環境需求
- **作業系統**: Windows 10/11
- **螢幕解析度**: 1920x1080 (建議)
- **Python 虛擬環境**: 強烈建議使用

---

## ⚙️ 配置系統

### 策略配置 (configs/strategy.json)
```json
{
    "unit": 1150,                  // 基本單位金額
    "target": "AUTO",              // 下注目標（AUTO/P/B）
    "martingale": {
        "enabled": true,           // 啟用馬丁格爾
        "max_level": 7,           // 最大級數
        "reset_on_win": true,     // 獲勝重置
        "progression": [1,2,4,8,16,32,64]  // 倍投序列
    },
    "risk_control": {
        "max_loss": 5000,         // 最大虧損
        "max_win": 3000,          // 最大獲利
        "session_limit": 50,      // 會話局數限制
        "consecutive_loss_limit": 5  // 連續失敗限制
    },
    "betting_logic": {
        "follow_trend": true,      // 跟隨趨勢
        "switch_after_losses": 3,  // 失敗後切換
        "skip_tie": true          // 跳過和局
    }
}
```

### 位置配置 (configs/positions.json)
```json
{
    "version": 2,
    "screen": {
        "width": 1920,
        "height": 1080,
        "dpi_scale": 1.0
    },
    "points": {
        "banker": {"x": 84, "y": 763},
        "player": {"x": 396, "y": 782},
        "tie": {"x": 688, "y": 769},
        "chip_1k": {"x": 107, "y": 903},
        "confirm": {"x": 990, "y": 760},
        "cancel": {"x": 1429, "y": 773}
    },
    "roi": {
        "overlay": {"x": 195, "y": 575, "w": 104, "h": 29},
        "timer": {"x": 522, "y": 621, "w": 55, "h": 59}
    },
    "overlay_params": {
        "consecutive_required": 1,
        "ncc_threshold": 0.6,
        "template_paths": {
            "qing": "path/to/qing_template.png",
            "jie": "path/to/jie_template.png",
            "fa": "path/to/fa_template.png"
        }
    }
}
```

---

## 🎮 UI 功能模組

### 頁面架構
```
🏠 首頁 (page_home.py)          - 快速啟動、專案概覽
🖼️ 模板管理 (page_templates.py)  - 模板驗證、品質檢查
📍 位置校準 (page_positions.py)  - 座標捕獲、ROI 設定
🎯 可下注判斷 (page_overlay.py)   - 偵測器測試、參數調整
⚙️ 策略設定 (page_strategy.py)   - 策略配置、馬丁格爾設定
🎮 實戰主控台 (page_dashboard.py) - 引擎控制、即時監控
📡 事件來源 (page_events.py)     - Demo/NDJSON 事件源
📊 記錄回放 (page_sessions.py)   - 歷史記錄、統計分析
🔧 系統設定 (page_settings.py)   - 全域配置、環境變數
```

### 關鍵 UI 組件

#### StatusCard (Dashboard)
```python
class StatusCard(QFrame):
    """狀態卡片 - 顯示引擎狀態"""
    def update_content(self, content: str, color: str = "#ffffff")
```

#### LogViewer (Dashboard)
```python
class LogViewer(QFrame):
    """日誌檢視器 - 即時日誌顯示"""
    def add_log(self, level: str, message: str)
```

#### EngineWorker (Background)
```python
class EngineWorker(QObject):
    """引擎工作執行緒 - 狀態監控與事件處理"""
    status_updated = Signal(dict)
    log_message = Signal(str, str)
```

---

## 🤖 核心引擎系統

### 狀態機流程 (autobet_engine.py)
```
idle → betting_open → placing_bets → wait_confirm → in_round → eval_result → idle
  ↑                                                      ↓
  ←-------------- 錯誤處理/暫停 ←-----------------------
```

### 主要狀態說明
- **idle**: 待機狀態，等待下注期開啟
- **betting_open**: 下注期開啟，準備下注計劃
- **placing_bets**: 執行下注動作（點擊籌碼、下注區）
- **wait_confirm**: 等待確認送單（實戰模式）
- **in_round**: 局內等待，等待結果事件
- **eval_result**: 評估結果，更新統計與策略

### 關鍵方法
```python
class AutoBetEngine:
    def set_enabled(self, flag: bool):          # 啟用/停用引擎
    def on_event(self, evt: Dict):              # 處理外部事件
    def _tick(self):                            # 主狀態機循環
    def _prepare_betting_plan(self) -> bool:    # 準備下注計劃
    def _execute_betting_plan(self):            # 執行下注
    def _handle_result(self, evt: Dict):        # 處理結果
    def get_status(self) -> Dict:               # 取得狀態
```

---

## 👁️ 偵測系統

### 偵測器架構

#### RobustOverlayDetector (完整版)
- **用途**: 開發與測試環境
- **技術**: HSV 顏色閘控 + 多尺度 NCC + Dice 係數
- **特色**: 抗干擾強、準確度高、計算成本較高

#### ProductionOverlayDetector (生產版)
- **用途**: 實戰環境（目前預設）
- **技術**: 雙閾值滯後 + 連續幀驗證
- **特色**: 快速穩定、資源占用低

#### OverlayDetectorWrapper (相容層)
- **用途**: 向下相容舊介面
- **技術**: 適配器模式
- **特色**: 無縫切換、保持 API 一致

### 核心演算法

#### 滯後決策邏輯
```python
def overlay_is_open(self) -> bool:
    confidence = self.calculate_confidence(frame)

    if confidence > self.open_threshold:
        self.open_counter += 1
        self.close_counter = 0
        if self.open_counter >= self.k_open:
            return True
    elif confidence < self.close_threshold:
        self.close_counter += 1
        self.open_counter = 0
        if self.close_counter >= self.k_close:
            return False

    return self.current_state == "OPEN"
```

#### HSV 顏色閘控
```python
def passes_color_gate(self, hsv_region: np.ndarray) -> bool:
    for gate_name, params in self.color_gates.items():
        if self.check_color_range(hsv_region, params):
            return True
    return False
```

---

## 🚀 部署與使用

### 快速啟動指令

#### 1. 環境準備
```bash
# 建立虛擬環境
python -m venv .venv
.venv\Scripts\activate

# 安裝依賴
pip install -r requirements.txt
```

#### 2. 位置校準
```bash
# GUI 模式（推薦）
python run_gui.py
# 進入 "📍 位置校準" 頁面

# 或命令行模式
python scripts/capture_positions.py
```

#### 3. 乾跑測試
```bash
# GUI 模式（推薦）
python run_gui.py
# 進入 "🎮 實戰主控台" 頁面

# 或命令行模式
python -m src.autobet.run_bot --dry-run
```

#### 4. 實戰部署（謹慎）
```bash
# 修改配置確保 unit 金額合理
# 編輯 configs/strategy.json

# 啟動實戰模式
python -m src.autobet.run_bot
```

### 驗證清單

#### 乾跑前檢查
- [ ] 位置校準完成 (`configs/positions.json` 存在)
- [ ] 策略配置合理 (`configs/strategy.json` 檢查)
- [ ] 模板品質良好 (NCC > 0.6)
- [ ] 偵測器正常運作 (GUI 測試)

#### 實戰前檢查
- [ ] 乾跑測試 30+ 局無錯誤
- [ ] 小額測試 (unit < 500)
- [ ] 嚴格限制 (max_loss < 2000)
- [ ] 人工監控準備就緒

---

## ⚠️ 已知問題與待辦

### 高優先級問題

#### 1. 位置校準批量化 (page_positions.py)
- **問題**: 目前需逐個點擊校準
- **影響**: 使用者體驗較差
- **解決方案**: 實現批量截圖 + 拖拽選擇

#### 2. HSV 參數介面 (page_overlay.py)
- **問題**: HSV 閾值需程式內調整
- **影響**: 除錯困難
- **解決方案**: 新增滑桿控制項與即時預覽

#### 3. 模板路徑自動檢測
- **問題**: 模板路徑寫死在配置中
- **影響**: 跨環境部署困難
- **解決方案**: 相對路徑 + 自動掃描

### 中優先級改進

#### 1. 日誌系統優化
- 新增日誌等級篩選
- 新增模組別篩選
- 新增匯出功能

#### 2. 統計面板增強
- 勝率計算
- 資金曲線圖
- 策略效果分析

#### 3. 備份還原機制
- 配置檔案備份
- 策略設定還原
- 位置配置匯入匯出

### 低優先級功能

#### 1. 多螢幕支援
- 螢幕選擇
- DPI 自動偵測
- 解析度適配

#### 2. 策略回測
- 歷史資料回放
- 策略效果模擬
- 參數最佳化

---

## 🗺️ 下階段路線圖

### Phase 1: 穩定性提升 (1-2 週)
- [ ] 完成位置校準批量化
- [ ] 完成 HSV 參數調整介面
- [ ] 修復模板路徑硬編碼問題
- [ ] 增強錯誤處理與恢復機制

### Phase 2: 功能完善 (2-3 週)
- [ ] 實現統計面板圖表化
- [ ] 新增配置備份還原
- [ ] 完善日誌系統
- [ ] 新增策略效果分析

### Phase 3: 效能優化 (1-2 週)
- [ ] 偵測演算法效能調優
- [ ] 記憶體使用最佳化
- [ ] 多執行緒效能調整
- [ ] 啟動速度改進

### Phase 4: 進階功能 (3-4 週)
- [ ] 多螢幕支援
- [ ] 策略回測系統
- [ ] 雲端配置同步
- [ ] API 介面開放

---

## 📞 技術支援與聯絡

### 檔案結構快速參考
```
關鍵檔案位置:
├── 主程式入口: src/autobet/run_bot.py, run_gui.py
├── 引擎核心: src/autobet/autobet_engine.py
├── 偵測系統: src/autobet/detectors.py
├── 配置管理: configs/*.json
├── UI 介面: ui/main_window.py, ui/pages/
└── 輔助工具: scripts/*.py
```

### 常見除錯位置
- **引擎狀態**: `autobet_engine.py:302` (get_status)
- **偵測日誌**: `detectors.py` (各 detector 類)
- **配置載入**: `run_bot.py:126` (load_positions)
- **UI 更新**: `ui/workers/engine_worker.py`

### 日誌檔案位置
- **執行日誌**: `data/logs/autobet.log`
- **會話記錄**: `data/sessions/session-*.csv`
- **事件記錄**: `data/sessions/events.out.ndjson`

---

**🎯 交接完成日期**: 2025-09-27
**下一位工程師**: 請先執行乾跑測試，熟悉 GUI 操作流程
**緊急問題**: 檢查日誌檔案與配置設定

---

*本文件將隨專案進展持續更新*
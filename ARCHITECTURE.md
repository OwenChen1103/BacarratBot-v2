# BacarratBot v2 - 架構設計文檔

## 當前問題

1. **職責重疊**: PhaseDetector 和 RoundManager 都在管理階段
2. **邏輯分散**: 下注、結算、信號發送散落在多個文件
3. **難以維護**: 信號鏈路複雜，調試困難

## 推薦架構

### 核心原則

1. **單一職責**: 每個組件只做一件事
2. **單向數據流**: 事件只能向下游傳播
3. **明確所有權**: 每個數據只有一個 source of truth

### 組件職責劃分

```
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Dashboard   │  │ NextBetCard  │  │  LogViewer   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         └──────────────────┼──────────────────┘              │
│                            │                                 │
└────────────────────────────┼─────────────────────────────────┘
                             │ Signals
┌────────────────────────────┼─────────────────────────────────┐
│                    Worker Layer                              │
│                    ┌────────────────┐                        │
│                    │ EngineWorker   │                        │
│                    │ (協調者)        │                        │
│                    └────────┬───────┘                        │
│                             │                                │
│                    ┌────────▼───────┐                        │
│                    │   EventBus     │  ← 中央事件總線        │
│                    │  (統一分發)     │                        │
│                    └────────┬───────┘                        │
│                             │                                │
└─────────────────────────────┼────────────────────────────────┘
                              │ Events
┌─────────────────────────────┼────────────────────────────────┐
│                    Core Layer                                │
│                                                              │
│  ┌─────────────────────────────────────────────────┐        │
│  │           RoundManager (局管理器)                │        │
│  │  職責:                                            │        │
│  │  - 生成和追蹤 round_id                           │        │
│  │  - 管理局的生命週期 (階段轉換)                    │        │
│  │  - 追蹤參與狀態 (is_participated)               │        │
│  └──────────────────┬──────────────────────────────┘        │
│                     │                                        │
│  ┌─────────────────▼────────────────────────────┐           │
│  │      StrategyEngine (策略引擎)                │           │
│  │  職責:                                         │           │
│  │  - 評估策略觸發                                │           │
│  │  - 生成下注決策                                │           │
│  │  - 管理策略狀態                                │           │
│  │  - 維護歷史記錄 (只記錄觀察局)                 │           │
│  └──────────────────┬──────────────────────────┘           │
│                     │                                        │
│  ┌─────────────────▼────────────────────────────┐           │
│  │      PositionManager (倉位管理器)             │           │
│  │  職責:                                         │           │
│  │  - 追蹤活躍倉位                                │           │
│  │  - 計算盈虧                                    │           │
│  │  - 管理資金                                    │           │
│  └──────────────────┬──────────────────────────┘           │
│                     │                                        │
│  ┌─────────────────▼────────────────────────────┐           │
│  │      ExecutionEngine (執行引擎)               │           │
│  │  職責:                                         │           │
│  │  - 規劃籌碼配方                                │           │
│  │  - 執行下注序列                                │           │
│  │  - 處理失敗和回滾                              │           │
│  └───────────────────────────────────────────────┘           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 事件流 (使用 EventBus)

```
1. BeadPlateResultDetector 檢測到結果
   ↓
   EventBus.publish(RESULT_DETECTED)
   ↓
2. RoundManager 訂閱 RESULT_DETECTED
   - 創建新局
   - 啟動階段計時器
   ↓
   EventBus.publish(PHASE_CHANGED, phase=BETTABLE)
   ↓
3. StrategyEngine 訂閱 PHASE_CHANGED
   - 評估策略觸發
   ↓
   EventBus.publish(STRATEGY_TRIGGERED)
   ↓
4. PositionManager 訂閱 STRATEGY_TRIGGERED
   - 創建倉位
   ↓
   EventBus.publish(BET_DECISION)
   ↓
5. ExecutionEngine 訂閱 BET_DECISION
   - 執行下注
   ↓
   EventBus.publish(BET_EXECUTED)
   ↓
6. RoundManager 訂閱 BET_EXECUTED
   - 標記參與局
   ↓
7. UI 訂閱 BET_EXECUTED
   - 顯示 NextBetCard
   ↓
8. 檢測到新結果
   ↓
   EventBus.publish(RESULT_DETECTED)
   ↓
9. PositionManager 訂閱 RESULT_DETECTED
   - 結算倉位
   ↓
   EventBus.publish(POSITION_SETTLED)
   ↓
10. StrategyEngine 訂閱 POSITION_SETTLED
    - 更新層數
    - 只有觀察局才記錄到歷史
   ↓
11. UI 訂閱 POSITION_SETTLED
    - 更新 NextBetCard 顯示結果
```

### 數據所有權

| 數據 | Owner | 其他組件如何訪問 |
|------|-------|------------------|
| round_id | RoundManager | 通過事件傳遞 |
| 局的階段 | RoundManager | 訂閱 PHASE_CHANGED |
| 參與狀態 | RoundManager | 查詢接口 |
| 策略觸發 | StrategyEngine | 發布 STRATEGY_TRIGGERED |
| 歷史記錄 | StrategyEngine | 只記錄觀察局 |
| 活躍倉位 | PositionManager | 訂閱 BET_DECISION |
| 盈虧計算 | PositionManager | 訂閱 RESULT_DETECTED |

## 重構路線圖

### 階段 1: 引入 EventBus (1-2天)
- ✅ 創建 EventBus
- 在 EngineWorker 中初始化
- 逐步遷移現有信號到 EventBus

### 階段 2: 重構 RoundManager (2-3天)
- 移除 PhaseDetector（功能合併到 RoundManager）
- RoundManager 負責計時 + 狀態管理
- 訂閱 RESULT_DETECTED，發布 PHASE_CHANGED

### 階段 3: 拆分 LineOrchestrator (3-5天)
- 創建 StrategyEngine（策略評估 + 歷史記錄）
- 創建 PositionManager（倉位追蹤 + 盈虧計算）
- 遷移 _pending、handle_result 邏輯

### 階段 4: 重構 EngineWorker (2-3天)
- 從"大雜燴"變成"協調者"
- 只負責啟動組件和連接 EventBus
- 不再直接處理業務邏輯

### 階段 5: UI 層解耦 (1-2天)
- UI 直接訂閱 EventBus
- 移除 EngineWorker 的信號中轉

## 當前可以做的最小改動

如果現在還不想大重構，至少可以：

1. ✅ **保留 RoundManager**（已完成）
   - 統一 round_id 生成
   - 追蹤參與狀態

2. **簡化 PhaseDetector**
   - 只保留計時功能
   - 移除 round_id 生成（由 RoundManager 負責）

3. **整理 LineOrchestrator.handle_result**
   - ✅ 參與局不記錄歷史（已完成）
   - 添加清晰的註釋

4. **添加架構文檔**
   - ✅ 記錄組件職責（本文件）
   - 記錄數據流

## P0 緊急修復（已完成）

> **完成日期**: 2025-10-24
> **測試驗證**: test_p0_fixes.py 全部通過 ✅

### 1. ✅ 移除過時的 net profit 追蹤

**問題**: `AutoBetEngine.net` 與 `LineOrchestrator` 的 PnL 計算重複，造成混淆。

**修復**:
- 移除 `AutoBetEngine.net` 屬性
- 移除 `get_status()` 中的 `net` 字段
- 更新 CSV 日誌格式（移除 net 欄位）
- 盈虧統一由 `LineOrchestrator` 計算

**影響文件**:
- `src/autobet/autobet_engine.py` (line 45, 57, 402, 433)

**測試**: `test_deprecated_net_removal()` ✅

---

### 2. ✅ 修復參與局排除邏輯

**問題**: 參與的局（有下注）仍被記錄到策略歷史，導致策略判斷錯誤。

**根本原因**: `LineOrchestrator.handle_result()` 先調用 `tracker.record()`，再檢查 `_pending`。

**修復**:
- 調整邏輯順序：**先檢查 `_pending`**，再決定是否記錄歷史
- 觀察局（無 pending position）→ 記錄到歷史
- 參與局（有 pending position）→ 不記錄，直接結算

**影響文件**:
- `src/autobet/lines/orchestrator.py` (line 445-476)

**測試**: `test_orchestrator_participation_exclusion()` ✅

**關鍵代碼**:
```python
# 先檢查是否有待處理倉位（參與局 vs 觀察局）
pending_key = (table_id, round_id, strategy_key)
position = self._pending.pop(pending_key, None)

if not position:
    # ✅ 觀察局：記錄到歷史
    tracker.record(table_id, round_id, winner_code or "", timestamp)
    continue

# ✅ 參與局：不記錄，直接結算
```

---

### 3. ✅ 統一 round_id 生成

**問題**: round_id 不一致導致倉位追蹤失敗
- PhaseDetector 生成: `detect-xxx_next`
- ResultDetector 生成: `detect-yyy`
- 下注時使用 `_next`，結算時找不到倉位

**修復**:
- 創建 `RoundManager` 統一管理 round_id
- 格式統一: `round-{table_id}-{timestamp_ms}`
- 移除 `_next` 後綴混淆
- 集成到 `EngineWorker`

**影響文件**:
- `src/autobet/round_manager.py` (新文件，line 84)
- `ui/workers/engine_worker.py` (line 1138-1152, 1462-1466)

**測試**:
- `test_round_manager_unified_ids()` ✅
- `test_round_manager_participation_tracking()` ✅

**關鍵改進**:
- ✅ round_id 格式統一
- ✅ 追蹤參與狀態 (`is_participated`)
- ✅ 提供 `should_include_in_history()` 判斷接口
- ✅ 標記下注和結算時間點

---

### 4. ✅ 乾跑模式修復

**問題**: 乾跑模式下點擊失敗會拋出異常，測試無法完整運行。

**修復**:
- 檢查 `engine.dry` 標誌
- 乾跑模式下允許點擊失敗，不拋出異常
- 保持所有其他邏輯（盈虧計算、歷史記錄）照常運行

**影響文件**:
- `ui/workers/engine_worker.py` (line 1353-1389)

**關鍵代碼**:
```python
is_dry_run = getattr(self.engine, 'dry', False)

click_result = self.engine.act.click_chip_value(chip.value)
if not click_result and not is_dry_run:  # 只在實戰模式拋異常
    raise Exception(f"點擊失敗: {chip_desc}")
```

---

### 驗證方式

運行集成測試:
```bash
python test_p0_fixes.py
```

**測試結果** (2025-10-24):
```
✅ PASSED: test_deprecated_net_removal
✅ PASSED: test_round_manager_unified_ids
✅ PASSED: test_round_manager_participation_tracking
✅ PASSED: test_orchestrator_participation_exclusion

總計: 4/4 測試通過
🎉 所有 P0 修復驗證通過！
```

---

## 長期目標

建立一個**清晰、可維護、易擴展**的架構：

- 新人可以快速理解代碼結構
- 添加新功能不會破壞現有功能
- 問題可以快速定位和修復
- 單元測試容易編寫

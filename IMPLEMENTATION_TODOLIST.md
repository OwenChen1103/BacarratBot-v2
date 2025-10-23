# 🎯 完整實作 TODOLIST

根據三個問題的分析，以下是完整的實作清單。

---

## ✅ 已完成

- [x] **Task 1**: 修改預設 Dedup 模式為 STRICT (`src/autobet/lines/config.py:49`)
- [x] **Task 2**: 確認賠率設定 (莊 0.95 / 閒 1.0 / 和 8.0)
- [x] **Task 3**: NextBetCard 整合結果局功能 (`ui/components/next_bet_card.py`)

---

## 🔴 待實作 (按順序執行)

### **Task 4: EngineWorker 新增信號**

**文件**: `ui/workers/engine_worker.py`

**步驟 4.1**: 新增 Signal 定義 (約 line 120)

```python
class EngineWorker(QThread):
    # ... 現有信號 ...
    next_bet_info = Signal(dict)

    # 🔥 新增以下兩個信號
    bet_executed = Signal(dict)        # 下注執行完成
    result_settled = Signal(str, float)  # 結果計算完成 (outcome, pnl)
```

---

**步驟 4.2**: 在 `_dispatch_line_order()` 發送 `bet_executed` 信號

**位置**: 約 line 1306 (confirm() 執行成功後)

```python
def _dispatch_line_order(self, decision: BetDecision) -> None:
    """執行 Line 策略產生的下注決策"""
    # ... 現有代碼 (執行點擊序列) ...

    try:
        # ... 點擊籌碼、下注區 ...

        # 確認下注
        self.engine.act.confirm()
        self._emit_log("INFO", "Line", f"✅ 訂單執行完成: {decision.strategy_key}")

        # 🔥 新增: 發送「下注已執行」信號
        if self._line_orchestrator:
            definition = self._line_orchestrator.strategies.get(decision.strategy_key)
            progression = self._line_orchestrator._get_progression(decision.table_id, decision.strategy_key)

            if definition and progression:
                self.bet_executed.emit({
                    "strategy": decision.strategy_key,
                    "direction": decision.direction.value.lower(),
                    "amount": decision.amount,
                    "current_layer": decision.layer_index + 1,
                    "total_layers": len(definition.staking.sequence),
                    "round_id": decision.round_id,
                    "sequence": list(definition.staking.sequence),
                    "on_win": "RESET" if definition.staking.reset_on_win else "ADVANCE",
                    "on_loss": "ADVANCE" if definition.staking.advance_on.value == "loss" else "RESET"
                })

    except Exception as e:
        # ... 現有錯誤處理 ...
```

---

**步驟 4.3**: 在 `_handle_event()` 發送 `result_settled` 信號

**位置**: 約 line 460 (handle_result 之後)

**在 `if self._line_orchestrator and table_id and round_id:` 區塊內新增**:

```python
# 調用 handle_result
self._line_orchestrator.handle_result(table_id, round_id, winner, ts_sec)

# 🔥 新增: 發送「結果已計算」信號
for strategy_key, line_state in self._line_orchestrator.line_states.get(table_id, {}).items():
    # 檢查是否有最近的結果
    if hasattr(line_state, 'layer_state') and line_state.layer_state.outcome:
        from src.autobet.lines.state import LayerOutcome

        outcome_map = {
            LayerOutcome.WIN: "win",
            LayerOutcome.LOSS: "loss",
            LayerOutcome.SKIPPED: "skip",
        }
        outcome_str = outcome_map.get(line_state.layer_state.outcome, "skip")

        # 計算 PnL (從 layer_state)
        stake = abs(line_state.layer_state.stake)
        if line_state.layer_state.outcome == LayerOutcome.WIN:
            # 使用賠率計算
            from src.autobet.payout_manager import PayoutManager
            pm = PayoutManager()
            # 從 pending 獲取方向
            for pending_key, position in self._line_orchestrator._pending.items():
                if pending_key[0] == table_id and pending_key[2] == strategy_key:
                    pnl = pm.calculate_pnl(stake, "WIN", position.direction.value)
                    break
            else:
                pnl = stake  # fallback
        elif line_state.layer_state.outcome == LayerOutcome.LOSS:
            pnl = -stake
        else:
            pnl = 0.0

        self.result_settled.emit(outcome_str, pnl)
        break  # 只處理第一個
```

**⚠️ 注意**: 上面的 PnL 計算較複雜，建議在 Task 5 完成後再實作。

---

### **Task 5: LineOrchestrator 整合 PayoutManager**

**文件**: `src/autobet/lines/orchestrator.py`

**步驟 5.1**: 導入 PayoutManager (文件開頭)

```python
# 在文件開頭新增
from src.autobet.payout_manager import PayoutManager
```

---

**步驟 5.2**: 在 `__init__` 初始化 PayoutManager (約 line 323)

```python
def __init__(self, ...):
    # ... 現有代碼 ...

    # 🔥 新增: 賠率管理器
    self.payout_manager = PayoutManager()
```

---

**步驟 5.3**: 修改 `_pnl_delta()` 使用 PayoutManager (約 line 850)

**將**:
```python
@staticmethod
def _pnl_delta(amount: float, outcome: LayerOutcome) -> float:
    if outcome == LayerOutcome.WIN:
        return float(amount)
    if outcome == LayerOutcome.LOSS:
        return float(-amount)
    return 0.0
```

**改為**:
```python
def _pnl_delta(self, amount: float, outcome: LayerOutcome, direction: BetDirection) -> float:
    """計算盈虧 (使用賠率管理器)"""
    return self.payout_manager.calculate_pnl(
        amount,
        outcome.name,  # "WIN" | "LOSS" | "SKIPPED"
        direction.value  # "B" | "P" | "T"
    )
```

---

**步驟 5.4**: 修改 `handle_result()` 傳遞 direction 參數 (約 line 493)

**將**:
```python
pnl_delta = self._pnl_delta(position.amount, outcome)
```

**改為**:
```python
pnl_delta = self._pnl_delta(position.amount, outcome, position.direction)
```

---

### **Task 6: 修正 EngineWorker 使用真實 PnL**

**文件**: `ui/workers/engine_worker.py`

**步驟 6.1**: 刪除模擬 PnL 代碼 (約 line 476-481)

**刪除**:
```python
# 模擬投注結果（這裡只是示例）
if winner in ["B", "P"]:
    # 模擬盈虧（隨機）
    import random
    profit = random.randint(-100, 150)
    self._net_profit += profit
```

---

**步驟 6.2**: 替換為真實 PnL 計算

**在相同位置新增**:
```python
# 🔥 使用真實 PnL (從 LineOrchestrator)
if self._line_orchestrator:
    # 累計所有 LineState 的 pnl
    total_pnl = 0.0
    for table_states in self._line_orchestrator.line_states.values():
        for line_state in table_states.values():
            total_pnl += line_state.pnl

    self._net_profit = total_pnl
```

---

### **Task 7: Dashboard 連接信號**

**文件**: `ui/pages/page_dashboard.py`

**步驟 7.1**: 連接新信號 (在 `__init__` 的信號連接區域)

```python
# 現有連接
self.worker.next_bet_info.connect(self._on_next_bet_info)

# 🔥 新增連接
self.worker.bet_executed.connect(self._on_bet_executed)
self.worker.result_settled.connect(self._on_result_settled)
```

---

**步驟 7.2**: 實作信號處理方法

```python
def _on_bet_executed(self, data: dict):
    """
    下注執行完成後，顯示結果局

    Args:
        data: {
            "strategy": "martingale_bpp",
            "direction": "banker",
            "amount": 200,
            "current_layer": 2,
            "total_layers": 4,
            "round_id": "...",
            "sequence": [100, 200, 400, 800],
            "on_win": "RESET",
            "on_loss": "ADVANCE"
        }
    """
    # 在 NextBetCard 顯示結果局
    self.next_bet_card.show_result_round(data)

    # 記錄日誌
    self._emit_log("INFO", "Dashboard",
                   f"📍 結果局啟動: {data.get('strategy')} {data.get('amount')}元")

def _on_result_settled(self, outcome: str, pnl: float):
    """
    結果計算完成後，更新結果局

    Args:
        outcome: "win" | "loss" | "skip"
        pnl: 盈虧金額
    """
    # 更新 NextBetCard 結果
    self.next_bet_card.update_result_outcome(outcome, pnl)

    # 記錄日誌
    self._emit_log("INFO", "Dashboard",
                   f"📊 結果計算: {outcome} PnL={pnl:+.0f}元")
```

---

### **Task 8: 執行測試**

**步驟 8.1**: 測試 ResultRoundCard 組件

```bash
# 執行 UI 測試
python test_result_round_card.py

# 測試項目:
# 1. 顯示莊家下注 → 卡片出現
# 2. 顯示閒家下注 → 卡片出現
# 3. 結果獲勝 → 卡片變綠，3秒後隱藏
# 4. 結果失敗 → 卡片變紅，3秒後隱藏
```

---

**步驟 8.2**: 測試 Dedup 模式和賠率計算

```bash
# 執行端到端測試
python test_e2e_workflow.py

# 預期輸出:
# ✅ Dedup 模式測試通過
# ✅ 賠率計算測試通過
# ✅ 完整工作流程測試通過
```

---

**步驟 8.3**: 實戰測試完整流程

```
1. 啟動 GUI
   python run_gui.py

2. 切換到 Dashboard

3. 啟動引擎 (模擬模式)

4. 觀察流程:
   ┌─────────────────────────────────────┐
   │ 1. ResultDetector 檢測到開獎結果     │
   │    → SignalTracker 記錄歷史          │
   └───────────────┬─────────────────────┘
                   ↓
   ┌─────────────────────────────────────┐
   │ 2. PhaseDetector 進入 BETTABLE 階段  │
   │    → LineOrchestrator 檢查入場條件   │
   └───────────────┬─────────────────────┘
                   ↓
   ┌─────────────────────────────────────┐
   │ 3. 模式匹配成功 (例: BPP)            │
   │    → 生成 BetDecision                │
   └───────────────┬─────────────────────┘
                   ↓
   ┌─────────────────────────────────────┐
   │ 4. _dispatch_line_order() 執行下注   │
   │    → bet_executed 信號發送           │
   │    → ✅ NextBetCard 顯示「結果局」   │
   └───────────────┬─────────────────────┘
                   ↓
   ┌─────────────────────────────────────┐
   │ 5. ResultDetector 檢測到新結果       │
   │    → handle_result() 計算 PnL        │
   │    → result_settled 信號發送         │
   │    → ✅ NextBetCard 更新結果 (獲勝/失敗) │
   │    → 3秒後自動隱藏                   │
   └─────────────────────────────────────┘

5. 驗證項目:
   ✅ 歷史 PPP 只觸發一次 (STRICT 模式)
   ✅ 莊家贏 100元 → PnL +95元
   ✅ 閒家贏 100元 → PnL +100元
   ✅ 和局 → PnL 0元 (層數不變)
   ✅ Dashboard 統計數字正確
   ✅ 結果局 UI 正確顯示和隱藏
```

---

## 🎯 測試檢查清單

### **Dedup 模式測試**

- [ ] 策略 "PP then bet B"，歷史 [P, P, P]
  - [ ] 第2個P 觸發 ✅
  - [ ] 第3個P 不觸發 ❌ (STRICT 模式)
- [ ] 策略 "BPP then bet B"，歷史 [B, P, P, B, P, P]
  - [ ] 第1個 BPP 觸發 ✅
  - [ ] 第2個 BPP 觸發 ✅ (完全新的序列)

### **賠率計算測試**

- [ ] 莊家贏 100元 → PnL = +95元
- [ ] 閒家贏 100元 → PnL = +100元
- [ ] 和局贏 100元 → PnL = +800元
- [ ] 失敗 100元 → PnL = -100元
- [ ] 押莊遇和局 → PnL = 0元 (退回)

### **結果局 UI 測試**

- [ ] 下注執行後，NextBetCard 顯示「結果局」區塊
- [ ] 顯示策略名稱、方向、金額、層數
- [ ] 顯示獲勝/失敗的影響預測
- [ ] 狀態燈閃爍 (800ms)
- [ ] 開獎後更新結果 (獲勝/失敗/和局)
- [ ] 邊框變色 (綠/紅/灰)
- [ ] 3秒後自動隱藏

### **整體流程測試**

- [ ] 策略觸發 → 下注執行 → 結果計算 → UI 更新
- [ ] PnL 統計正確 (Dashboard 顯示)
- [ ] 層數前進/重置邏輯正確
- [ ] 風控檢查 (止損/止盈) 生效
- [ ] 日誌輸出完整清晰

---

## 📝 注意事項

1. **執行順序**: 必須按 Task 4 → 5 → 6 → 7 → 8 順序執行
2. **測試頻率**: 每完成一個 Task 後立即測試
3. **回滾準備**: 如果出現錯誤，使用 Git 回滾到上一個穩定版本
4. **日誌檢查**: 所有關鍵步驟都應有日誌輸出，方便除錯

---

## 🚀 快速執行指令

```bash
# 1. 測試組件
python test_result_round_card.py

# 2. 測試邏輯
python test_e2e_workflow.py

# 3. 啟動 GUI
python run_gui.py

# 4. 檢查配置
cat configs/payout_rates.json
cat configs/line_strategies/*.json
```

---

## 📊 預期成果

完成所有 Task 後，系統應具備以下功能：

1. ✅ **STRICT 去重**: 避免歷史重疊觸發
2. ✅ **正確賠率**: 莊0.95、閒1.0、和8.0
3. ✅ **結果局 UI**: 清楚顯示已下注的局，預測輸贏影響
4. ✅ **真實 PnL**: Dashboard 統計數字來自真實計算
5. ✅ **完整工作流**: 從策略觸發到結果計算的全自動流程

---

**祝您實作順利！🎉**

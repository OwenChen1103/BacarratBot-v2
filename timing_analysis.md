# 結果局顯示時序分析

## 當前流程（問題現象）

### 場景：兩閒打莊（PP then bet B）

```
時間軸：
T1: 第1個 P 開出 → 記錄到歷史
T2: 第2個 P 開出 → 記錄到歷史 ✅ 此時歷史已是 [P, P]
T3: 系統檢測到「可下注」畫面
T4: 滑鼠移動到下注位置
T5: **此時才顯示「結果局」** ⚠️ 太晚了！
```

### 當前實現的詳細流程

#### 階段 1: 結果檢測（T2）
```python
# engine_worker.py Line 1264
round_id = self._game_state.on_result_detected(table_id, winner="P", timestamp=T2)

# 產生事件
event = {"type": "RESULT", "winner": "P", "round_id": round_id}
self._incoming_events.put(event)
```

#### 階段 2: 結果處理（T2）
```python
# engine_worker.py Line 443
def _handle_event(event):
    if event_type == "RESULT":
        # 調用 handle_result 更新歷史
        self._line_orchestrator.handle_result(table_id, round_id, winner="P", timestamp=T2)
        # ✅ 此時 SignalTracker.history 已包含 [P, P]

        # ❌ 但這裡不檢查觸發條件！
        # ❌ 不顯示「結果局」！
```

#### 階段 3: 階段變化（T3 - 檢測到可下注）
```python
# engine_worker.py Line 1039
def _on_phase_changed(table_id, round_id, phase="bettable", timestamp=T3):
    # 只更新階段，不生成決策
    self._line_orchestrator.update_table_phase(
        table_id, round_id, TablePhase.BETTABLE, timestamp,
        generate_decisions=False  # ❌ 這裡不觸發
    )
```

#### 階段 4: 可下注畫面處理（T3-T4）
```python
# engine_worker.py Line 812
def on_bettable_detected():
    # 明確要求生成決策
    decisions = self._line_orchestrator.update_table_phase(
        table_id, round_id, TablePhase.BETTABLE, timestamp,
        generate_decisions=True  # ✅ 這裡才觸發檢查
    )

    # orchestrator.py Line 287
    if phase == TablePhase.BETTABLE and generate_decisions:
        decisions = self._evaluate_and_decide(...)

    # entry_evaluator.py Line 202
    should_trigger_result = tracker.should_trigger(table_id, round_id, timestamp)
    # ✅ 檢查歷史 [P, P] 是否匹配模式 "PP"
    # ✅ 匹配成功！
```

#### 階段 5: 下注執行（T4-T5）
```python
# engine_worker.py Line 1539
# 發送 bet_executed 信號
self.bet_executed.emit({
    "strategy": "兩閒打莊",
    "direction": "banker",
    "amount": 100,
    ...
})
```

#### 階段 6: UI 顯示結果局（T5）
```python
# page_dashboard.py
# 收到 bet_executed 信號後才顯示
self.result_round_card.show_pending_bet(data)
```

---

## 問題分析

### 核心問題
**觸發檢查（should_trigger）延遲到「檢測可下注畫面」時才執行**

### 時序對比

| 事件 | 當前時間點 | 理想時間點 | 延遲 |
|------|----------|----------|------|
| 結果檢測 | T2 | T2 | 0 |
| 歷史更新 | T2 | T2 | 0 |
| **觸發檢查** | T4 ⚠️ | T2 ✅ | ~2-3秒 |
| 結果局顯示 | T5 ⚠️ | T2 ✅ | ~3-5秒 |

### 為什麼延遲？

**當前設計邏輯：**
```python
# 結果處理時：只更新歷史，不檢查觸發
_handle_event(RESULT) → handle_result() → SignalTracker.record()
                                         → ❌ 不調用 should_trigger()

# 可下注檢測時：才檢查觸發
on_bettable_detected() → update_table_phase(generate_decisions=True)
                       → evaluate_and_decide()
                       → should_trigger() ✅
```

**設計原因：**
- 分離關注點：結果處理 vs 決策生成
- 避免過早觸發（可能畫面還未進入可下注階段）
- 確保有 round_id 可用於下注

---

## 用戶期望行為

### 理想流程
```
T1: 第1個 P 開出 → 記錄
T2: 第2個 P 開出 → 記錄 → **立即檢查觸發** → **立即顯示結果局** ✅
T3: 檢測到可下注 → 執行下注
T4: 滑鼠移動完成
```

### 為什麼更直觀？

1. **即時反饋**
   - 用戶看到第2個P開出
   - 系統立即顯示「策略已觸發，準備下注」
   - 符合心理預期

2. **清晰的因果關係**
   - 看到結果 → 看到觸發
   - 不是「看到結果 → 等待 → 看到滑鼠動 → 才知道觸發」

3. **狀態透明**
   - 用戶知道系統已識別模式
   - 而不是「系統在幹嘛？為什麼還沒反應？」

---

## 改成結果出來就觸發的影響分析

### 改動方案

#### 方案 A: 在 handle_result 後立即檢查觸發
```python
# engine_worker.py Line 494
def _handle_event(event):
    if event_type == "RESULT":
        # 1. 更新歷史
        self._line_orchestrator.handle_result(table_id, round_id, winner, timestamp)

        # 2. ✅ 立即檢查是否有策略觸發（僅用於 UI 顯示）
        triggered_strategies = self._check_triggered_strategies(table_id, timestamp)

        # 3. ✅ 如果有觸發，立即發送信號顯示結果局
        if triggered_strategies:
            self._emit_trigger_signal(triggered_strategies)
```

#### 方案 B: 在 SignalTracker.record 後自動檢查
```python
# signal.py Line 29
def record(self, table_id, round_id, winner, ts):
    ts = ts or time.time()
    deque = self.history[table_id]
    deque.append((winner, ts))

    # ✅ 立即檢查是否觸發
    if self.should_trigger(table_id, round_id, ts):
        return True  # 返回觸發狀態
    return False
```

---

### 潛在問題分析

#### ❌ 問題 1: round_id 不一致
**症狀：**
- T2 結果檢測創建 round-T2
- T3 可下注檢測創建 round-T3（新局）
- 如果 T2 就顯示結果局，用的是 round-T2
- 但實際下注時用的是 round-T3
- 可能導致結算時找不到對應的倉位

**嚴重程度：** 🔴 高

**解決方案：**
- 使用「預觸發」概念：T2 顯示「即將觸發」，但不創建倉位
- 實際下注仍在 T3 進行，使用正確的 round_id

#### ❌ 問題 2: 重複觸發檢查
**症狀：**
- T2: handle_result → 檢查觸發（結果：觸發）
- T3: on_bettable_detected → 檢查觸發（結果：觸發）
- 可能造成重複顯示或重複下注

**嚴重程度：** 🟡 中

**解決方案：**
- 去重機制已存在（DedupMode.OVERLAP）
- 但需要確保 UI 也不重複顯示

#### ❌ 問題 3: 狀態不一致
**症狀：**
- T2: 顯示結果局（phase = ARMED）
- T3: 實際下注（phase = WAITING_RESULT）
- 如果 T3 沒有檢測到可下注，結果局會一直顯示

**嚴重程度：** 🟡 中

**解決方案：**
- 結果局有超時機制（3秒後隱藏）
- 或在 T3 確認下注後才從 ARMED → ENTERED

#### ✅ 問題 4: 性能影響
**症狀：**
- 每次結果都要檢查所有策略的觸發條件

**嚴重程度：** 🟢 低

**理由：**
- should_trigger 很輕量（只檢查最近幾個結果）
- 策略數量有限（通常 < 10）
- 性能影響可忽略

#### ✅ 問題 5: 邏輯複雜度
**症狀：**
- 觸發檢查邏輯出現在兩個地方

**嚴重程度：** 🟢 低

**理由：**
- 用途不同：T2 是「預告」，T3 是「執行」
- 可以通過清晰的命名區分

---

## 結論

### 會有很多地方出問題嗎？

**答案：不會，但需要謹慎處理 round_id 一致性**

### 關鍵風險

| 問題 | 嚴重性 | 解決難度 | 建議方案 |
|------|-------|---------|---------|
| round_id 不一致 | 🔴 高 | 中 | 使用「預觸發」UI 狀態 |
| 重複觸發檢查 | 🟡 中 | 低 | 依賴現有去重機制 |
| 狀態不一致 | 🟡 中 | 低 | UI 超時 + 狀態同步 |
| 性能影響 | 🟢 低 | - | 無需處理 |
| 邏輯複雜度 | 🟢 低 | - | 清晰命名 |

### 建議實現方式

**推薦：方案 A +「預觸發」狀態**

1. **T2 結果檢測後：**
   - 檢查 should_trigger()
   - 如果觸發 → 發送 `strategy_pre_triggered` 信號
   - UI 顯示「策略已觸發，等待下注時機」（不創建倉位）

2. **T3 可下注檢測時：**
   - 正常執行現有邏輯
   - 生成決策 → 創建倉位 → 下注
   - UI 從「預觸發」→「已下注」

3. **好處：**
   - ✅ 用戶立即看到觸發（符合直覺）
   - ✅ round_id 一致性（倉位在 T3 創建）
   - ✅ 不破壞現有邏輯
   - ✅ 僅增加 UI 顯示層的提前通知

---

## 下一步

1. 實現「預觸發」檢查邏輯
2. 新增 `strategy_pre_triggered` 信號
3. UI 支持「預觸發」狀態顯示
4. 測試 round_id 一致性
5. 測試去重機制

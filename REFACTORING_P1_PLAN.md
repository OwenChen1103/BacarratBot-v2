# P1 重要重構計劃

> **優先級**: P1 (重要，1-2週內完成)
> **目標**: 解決核心架構問題，降低維護成本

## 概述

P1 重構專注於解決最嚴重的架構問題：
1. **God Class 拆分** - LineOrchestrator (1069行) 和 EngineWorker (1517行)
2. **職責重疊消除** - PhaseDetector vs RoundManager
3. **EventBus 引入** - 統一事件管理，減少信號鏈路

## 任務分解

### Task 1: 拆分 LineOrchestrator (3-5天)

**當前問題**:
- LineOrchestrator 有 1069 行，職責過多
- 混合了策略評估、倉位管理、盈虧計算、風控檢查

**重構目標**:
拆分為 5 個獨立組件：

#### 1.1 創建 StrategyRegistry (1天)

**職責**: 策略定義管理和查詢

**接口**:
```python
class StrategyRegistry:
    def __init__(self, strategies: Dict[str, StrategyDefinition]):
        """初始化策略註冊表"""

    def get_strategy(self, strategy_key: str) -> Optional[StrategyDefinition]:
        """獲取策略定義"""

    def get_strategies_for_table(self, table_id: str) -> List[Tuple[str, StrategyDefinition]]:
        """獲取適用於指定桌號的策略"""

    def list_all_strategies(self) -> Dict[str, StrategyDefinition]:
        """列出所有策略"""
```

**遷移內容**:
- `LineOrchestrator.strategies` → `StrategyRegistry._strategies`
- `LineOrchestrator._strategies_for_table()` → `StrategyRegistry.get_strategies_for_table()`

**影響範圍**: 低
**測試**: 單元測試 + 集成測試

---

#### 1.2 創建 EntryEvaluator (1-2天)

**職責**: 策略觸發條件評估

**接口**:
```python
class EntryEvaluator:
    def __init__(self, registry: StrategyRegistry, signal_trackers: Dict[str, SignalTracker]):
        """初始化評估器"""

    def evaluate_entries(self, table_id: str, timestamp: float) -> List[LineOrder]:
        """評估所有策略的入場條件"""

    def _should_trigger(
        self,
        table_id: str,
        strategy_key: str,
        definition: StrategyDefinition,
        line_state: LineState
    ) -> bool:
        """判斷單個策略是否應觸發"""
```

**遷移內容**:
- `LineOrchestrator._evaluate_entries()` → `EntryEvaluator.evaluate_entries()`
- `LineOrchestrator._should_trigger()` → `EntryEvaluator._should_trigger()`
- `LineOrchestrator.signal_trackers` → `EntryEvaluator.signal_trackers`

**影響範圍**: 中
**測試**: 單元測試（mock SignalTracker） + 集成測試

---

#### 1.3 創建 PositionManager (1-2天)

**職責**: 倉位生命週期管理和盈虧計算

**接口**:
```python
class PositionManager:
    def __init__(self):
        """初始化倉位管理器"""

    def create_position(self, order: LineOrder) -> PendingPosition:
        """創建待處理倉位"""

    def settle_position(
        self,
        table_id: str,
        round_id: str,
        strategy_key: str,
        winner: str
    ) -> Tuple[LayerOutcome, float]:
        """結算倉位，返回 (結果, PnL變化)"""

    def get_pending(self, table_id: str, round_id: str, strategy_key: str) -> Optional[PendingPosition]:
        """獲取待處理倉位"""

    def has_pending(self, table_id: str, strategy_key: str) -> bool:
        """檢查是否有待處理倉位"""
```

**遷移內容**:
- `LineOrchestrator._pending` → `PositionManager._positions`
- `LineOrchestrator._determine_outcome()` → `PositionManager._determine_outcome()`
- `LineOrchestrator._pnl_delta()` → `PositionManager._calculate_pnl_delta()`
- `LineOrchestrator.handle_result()` 中的結算邏輯 → `PositionManager.settle_position()`

**影響範圍**: 高
**測試**: 單元測試（完整覆蓋 W/L/T 所有情況） + 集成測試

---

#### 1.4 保持 RiskCoordinator 和 ConflictResolver (0.5天)

**決策**: 這兩個組件已經相對獨立，暫不拆分

**改進**:
- 添加完整的單元測試
- 增強文檔註釋

**影響範圍**: 低

---

#### 1.5 創建新的 LineOrchestrator (1天)

**職責**: 協調各組件，提供統一接口

**接口**:
```python
class LineOrchestrator:
    def __init__(
        self,
        registry: StrategyRegistry,
        evaluator: EntryEvaluator,
        positions: PositionManager,
        risk: RiskCoordinator,
        resolver: ConflictResolver,
        metrics: MetricsAggregator
    ):
        """初始化協調器"""

    def tick(self, table_id: str, timestamp: float) -> List[LineOrder]:
        """主循環：評估策略並返回下注決策"""
        return self.evaluator.evaluate_entries(table_id, timestamp)

    def handle_result(self, table_id: str, round_id: str, winner: str, timestamp: float):
        """處理結果：結算倉位並更新歷史"""
        # 協調 PositionManager 和 SignalTracker
```

**預期效果**:
- LineOrchestrator: 1069行 → ~200行（主要是協調邏輯）
- 新增 4 個獨立組件，每個 100-300 行
- 單元測試覆蓋率提升到 80%+

---

### Task 2: 合併 PhaseDetector 和 RoundManager (2-3天)

**當前問題**:
- PhaseDetector 負責計時和階段轉換
- RoundManager 負責 round_id 生成和參與狀態追蹤
- 職責重疊：都管理「局」的概念

**重構方案**: 創建統一的 GameStateManager

#### 2.1 設計 GameStateManager (0.5天)

**職責**: 統一管理局的生命週期和階段轉換

**接口**:
```python
class GameStateManager(QObject):
    # 信號
    phase_changed = Signal(str, str, str, float)  # (table_id, round_id, phase, timestamp)
    result_confirmed = Signal(str, str, str, float)  # (table_id, round_id, winner, timestamp)

    def __init__(self, parent=None):
        """初始化遊戲狀態管理器"""

    def on_result_detected(self, table_id: str, winner: str, detected_at: float) -> str:
        """處理結果檢測"""
        # 1. 生成統一的 round_id
        # 2. 創建新 Round 對象
        # 3. 啟動階段計時器
        # 4. 發送 result_confirmed 信號

    def mark_bet_placed(self, table_id: str, round_id: str):
        """標記某局已下注（參與局）"""

    def should_include_in_history(self, table_id: str, round_id: str) -> bool:
        """判斷某局是否應計入策略歷史"""

    def get_current_round(self, table_id: str) -> Optional[Round]:
        """獲取當前局"""
```

**關鍵改進**:
- ✅ 統一 round_id 生成（保留現有格式）
- ✅ 統一階段轉換邏輯（SETTLING → BETTABLE → LOCKED）
- ✅ 統一參與狀態追蹤
- ✅ 移除 PhaseDetector 的 "_next" 後綴生成邏輯

---

#### 2.2 實現 GameStateManager (1天)

**遷移內容**:
- `RoundManager.on_result_detected()` → `GameStateManager.on_result_detected()`
- `RoundManager.mark_bet_placed()` → `GameStateManager.mark_bet_placed()`
- `RoundManager.should_include_in_history()` → `GameStateManager.should_include_in_history()`
- `PhaseDetector._on_settling_complete()` → `GameStateManager._on_settling_complete()`
- `PhaseDetector._on_bettable_complete()` → `GameStateManager._on_bettable_complete()`
- `PhaseDetector._on_locked_complete()` → `GameStateManager._on_locked_complete()`

**時間配置**（可調整）:
```python
SETTLING_DURATION = 2.0    # 結算期
BETTABLE_DURATION = 10.0   # 下注期
LOCKED_DURATION = 5.0      # 鎖定期
```

---

#### 2.3 集成到 EngineWorker (0.5天)

**修改內容**:
```python
# ui/workers/engine_worker.py

# 移除
self._round_manager = RoundManager(parent=self)
self._phase_detector = PhaseDetector(parent=self)

# 新增
self._game_state = GameStateManager(parent=self)

# 信號連接
self._game_state.phase_changed.connect(self._on_phase_changed)
self._game_state.result_confirmed.connect(self._on_result_confirmed)
```

**影響範圍**: 中
**測試**: 集成測試（確保階段轉換和 round_id 生成正常）

---

#### 2.4 清理舊代碼 (0.5天)

- 刪除 `src/autobet/phase_detector.py`
- 刪除 `src/autobet/round_manager.py`
- 更新所有引用（grep 搜索 `PhaseDetector` 和 `RoundManager`）

---

### Task 3: 引入 EventBus 統一事件管理 (1-2天)

**當前問題**:
- 14層信號鏈路（BeadPlateResultDetector → ... → NextBetCard）
- 事件流不清晰，調試困難
- 組件間緊耦合

**重構方案**: 使用 EventBus 解耦組件通信

#### 3.1 完善 EventBus 實現 (0.5天)

**當前狀態**: `src/autobet/core/event_bus.py` 已創建，需要完善

**改進**:
- 添加異步發布支持（可選）
- 添加事件過濾器（防止循環發布）
- 添加性能監控（事件處理時間）

**接口完善**:
```python
class EventBus:
    def subscribe_once(self, event_type: EventType, callback: Callable) -> None:
        """訂閱一次性事件"""

    def unsubscribe(self, event_type: EventType, callback: Callable) -> None:
        """取消訂閱"""

    def publish_async(self, event: Event) -> None:
        """異步發布事件（可選）"""
```

---

#### 3.2 遷移核心事件到 EventBus (1天)

**遷移計劃**（漸進式）:

##### 階段 1: 結果檢測事件
```python
# 舊: BeadPlateResultDetector.result_detected (Signal)
# 新: EventBus.publish(RESULT_DETECTED)

event_bus.publish(Event(
    type=EventType.RESULT_DETECTED,
    timestamp=time.time(),
    source="BeadPlateResultDetector",
    data={"table_id": table_id, "winner": winner}
))
```

**訂閱者**:
- GameStateManager (創建新局)
- LineOrchestrator (處理結果)

---

##### 階段 2: 階段變化事件
```python
# 舊: GameStateManager.phase_changed (Signal)
# 新: EventBus.publish(PHASE_CHANGED)

event_bus.publish(Event(
    type=EventType.PHASE_CHANGED,
    timestamp=time.time(),
    source="GameStateManager",
    data={"table_id": table_id, "round_id": round_id, "phase": "BETTABLE"}
))
```

**訂閱者**:
- LineOrchestrator (觸發策略評估)
- Dashboard (更新 UI)

---

##### 階段 3: 下注決策事件
```python
# 舊: LineOrchestrator 返回 List[LineOrder]
# 新: EventBus.publish(STRATEGY_TRIGGERED)

event_bus.publish(Event(
    type=EventType.STRATEGY_TRIGGERED,
    timestamp=time.time(),
    source="EntryEvaluator",
    data={"orders": orders}
))
```

**訂閱者**:
- EngineWorker (執行下注)
- Dashboard (更新 NextBetCard)

---

##### 階段 4: 下注執行事件
```python
# 舊: EngineWorker._on_bet_executed (內部方法)
# 新: EventBus.publish(BET_EXECUTED)

event_bus.publish(Event(
    type=EventType.BET_EXECUTED,
    timestamp=time.time(),
    source="EngineWorker",
    data={"decision": decision, "bet_plan": bet_plan}
))
```

**訂閱者**:
- GameStateManager (標記參與局)
- NextBetCard (顯示下注信息)

---

##### 階段 5: 結算事件
```python
# 舊: PositionManager 內部邏輯
# 新: EventBus.publish(POSITION_SETTLED)

event_bus.publish(Event(
    type=EventType.POSITION_SETTLED,
    timestamp=time.time(),
    source="PositionManager",
    data={"outcome": outcome, "pnl_delta": pnl_delta}
))
```

**訂閱者**:
- Dashboard (更新 PnL 顯示)
- MetricsAggregator (記錄統計)

---

#### 3.3 更新 EngineWorker (0.5天)

**變化**:
- 初始化 EventBus（全局單例或傳遞給各組件）
- 移除直接的信號連接
- 訂閱必要的事件

```python
class EngineWorker(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 創建 EventBus
        self.event_bus = EventBus()

        # 創建組件（注入 EventBus）
        self._game_state = GameStateManager(event_bus=self.event_bus)
        self._orchestrator = LineOrchestrator(event_bus=self.event_bus, ...)

        # 訂閱事件
        self.event_bus.subscribe(EventType.STRATEGY_TRIGGERED, self._execute_bets)
        self.event_bus.subscribe(EventType.BET_EXECUTED, self._on_bet_executed)
```

---

## 預期效果

### 代碼量變化
- **LineOrchestrator**: 1069行 → ~200行協調邏輯 + 4個新組件（共~800行）
- **EngineWorker**: 1517行 → ~500行（移除業務邏輯，保留執行邏輯）
- **GameStateManager**: 新增 ~300行（合併 RoundManager + PhaseDetector）

### 架構改進
- ✅ 信號鏈路: 14層 → ~5層（通過 EventBus）
- ✅ 單元測試覆蓋率: <30% → >80%
- ✅ 職責清晰：每個類 < 400 行，單一職責
- ✅ 可觀測性：EventBus 提供完整的事件歷史

### 維護成本
- ✅ 新增策略觸發模式：只修改 EntryEvaluator
- ✅ 修改倉位結算邏輯：只修改 PositionManager
- ✅ 調整階段時間：只修改 GameStateManager 配置

---

## 風險評估

### 高風險
- **PositionManager 拆分**: 結算邏輯複雜，測試必須全面覆蓋

**緩解措施**:
- 編寫全面的單元測試（W/L/T 所有組合）
- 保留 `test_p0_fixes.py` 作為回歸測試
- 分支開發，充分測試後再合併

### 中風險
- **EventBus 引入**: 可能影響性能（每個事件多次回調）

**緩解措施**:
- 性能測試（1000次事件發布/訂閱的延遲）
- 可選異步發布（避免阻塞主線程）
- 保留 Signal 作為 UI 層通信（PySide6 原生支持）

### 低風險
- **StrategyRegistry 和 EntryEvaluator**: 邏輯簡單，容易測試

---

## 實施順序

1. **Week 1**: Task 1.1-1.3 (StrategyRegistry, EntryEvaluator, PositionManager)
2. **Week 1-2**: Task 1.5 (新 LineOrchestrator 協調器)
3. **Week 2**: Task 2 (合併 PhaseDetector + RoundManager → GameStateManager)
4. **Week 2**: Task 3 (引入 EventBus，漸進式遷移)

---

## 驗證標準

### 功能驗證
- ✅ `test_p0_fixes.py` 全部通過（回歸測試）
- ✅ 新增單元測試覆蓋率 > 80%
- ✅ 乾跑模式完整測試（10個策略 x 100局）

### 性能驗證
- ✅ EventBus 延遲 < 1ms
- ✅ 策略評估延遲 < 100ms
- ✅ 記憶體佔用無明顯增加

### 可維護性驗證
- ✅ 每個類 < 400 行
- ✅ 文檔覆蓋率 100%（所有公開接口）
- ✅ 新人可在 1 天內理解核心流程

---

## 下一步行動

1. **Review 本計劃**: 與團隊討論可行性和優先級
2. **創建 Git Branch**: `feature/p1-refactor-line-orchestrator`
3. **開始 Task 1.1**: 創建 StrategyRegistry（最低風險）
4. **持續集成**: 每完成一個 Task，運行 `test_p0_fixes.py`

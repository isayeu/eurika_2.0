# Память — минимальная формализация (Review III)

Три хранилища для автономного цикла. Без сложной иерархии.

---

## 1. EventLog

| Атрибут | Значение |
|--------|----------|
| **Реализация** | `EventStore` (eurika/storage/event_engine, events.py) |
| **Файл** | `.eurika/events.json` |
| **Контракт** | append-only; `append_event(type, input, output, result)`; `by_type(t)`, `recent_events(limit, types)` |
| **Типы событий** | `scan`, `patch`, `learn`, `feedback` |
| **Роль** | Первичный журнал: что произошло за все циклы |

**Точка входа:** `ProjectMemory(project_root).events` или `event_engine(project_root)`.

---

## 2. FailureLog

| Атрибут | Значение |
|--------|----------|
| **Реализация** | Bounded view над EventLog (learn, result=False) |
| **Файл** | Нет отдельного. Данные в `.eurika/events.json` |
| **Контракт** | `get_recent_failures`, `get_recent_failures_enriched`, `get_recent_failed_plan_hashes` |
| **Обогащение** | goal_id, plan_hash, confidence в output learn event (archive/ARCHITECTURE_MEMORY_REVIEW §2) |
| **Ограничение** | Bounded по limit при чтении |
| **Роль** | Провалы для самокоррекции; planner deprioritize; decay failure_penalty |

**Один источник истины:** все outcomes в EventLog. FailureLog = projection.

---

## 3. LearningStore

| Атрибут | Значение |
|--------|----------|
| **Реализация** | `LearningView` (event_views) — view над EventStore type=learn |
| **Запись** | `record_outcome(..., delta_energy=...)` → memory.learning.append; learn event output: delta_energy, failure_reason, goal_id, plan_hash |
| **Чтение** | `aggregate_by_action_kind()`, `aggregate_by_smell_action()`, `get_merged_learning_stats(root)` |
| **Роль** | Агрегаты success/fail по (smell_type, action_kind); planner сортирует ops по learning_stats |
| **last_ts** | В каждом stats entry — timestamp последнего события (подготовка к age-based decay, ROADMAP §4.5) |
| **S5 context** | `record_outcome(..., project_size=, module_size=, context=)` — контекст для outcome, avoid «свалка без контекста» |

**Точка входа:** `ProjectMemory(project_root).learning`; `eurika.storage.record_outcome`; `get_merged_learning_stats` (global_memory).

---

## Learning Loop (R5 — центральность)

Замкнутый цикл: Apply → Learn → Plan (читает) → Apply...

```
[Fix Cycle N]
  Apply  → patch_engine.apply_and_verify
  Verify → success/fail
  Learn  → record_outcome(modules, ops, risks, verify_success, delta_energy)
         → adapt_weights_from_experience (default on; EURIKA_WEIGHT_ADAPTATION=0 отключает)

[Fix Cycle N+1]
  Plan   → get_merged_learning_stats(root) → learning_stats
         → planner: filter_policy, sort_by_learning, deprioritize failures
         → graph_ops: priority_from_graph(learning_stats=...)
  Input  → scan, diagnose (summary, smells)
  ...
```

**Точки входа:** `record_outcome`, `get_merged_learning_stats`, `adapt_weights_from_experience` (включено по умолчанию).

### ML (PyTorch) и рестарт

Опыт **не** должен пропадать при перезапуске Qt / Ollama / процесса Eurika.

| Что | Где живёт | После рестарта |
|-----|-----------|----------------|
| Learning loop (уже есть) | `.eurika/events.json`, learning/experience stores | читается Plan’ом |
| Market ML (paper) | `.eurika/ml/market/`, `paper_trades.jsonl`, `weights/market_policy.pt`, **`market_journal.jsonl`** (лента Market) | sync/paper/train/status; журнал читается с диска |

`eurika ml-market`: свечи Binance → paper BUY/SELL → метка correct/incorrect по горизонту → CPU **MLP** entry policy. **Live-ордера нет.** `train_accuracy` — in-sample на `paper_trades.jsonl`, не walk-forward.

**Продукт / ops:** цель оболочки — [VISION.md](VISION.md). Скелет (метки, банк, verify, journal) — наш; **научиться зарабатывать** — её (опыт → веса/политика). Soft-entry (`model/soft`: HOLD<0.55 + сторона≥0.24) и exit-first (`should_model_exit`, frac TP 0.25, trail×0.75) — рычаги скелета для прибыли при explore off, не финальная «стратегия навсегда». После `exit_reason=model` — cooldown **20×1m** на ту же сторону (`reentry_cooldown.json`). Корень — `eurika_2.0.Qt`.

**Paper bank 1000 USDT** — риск 1% equity на сделку (маржа); futures lev 1…5× = **уверенность** (side prob), vol слегка гасит; суммарная маржа ≤30% equity; PnL USDT = edge×notional. **Комиссии:** spot `0.001` RT; futures `0.0008` RT. **Funding:** при закрытии futures — public Binance `fundingRate` (settlements в окне) или pro-rata `lastFundingRate` из `premiumIndex`; знаковый edge (`fund=…[history|premium_prorata]`). Cash-and-carry / фарм — отдельный режим.

**Dual TF:** сигнал и фичи на основном ТФ (`15m`/`1h`); вход/выход на **`1m`** с TP/SL по high/low (если оба в одном баре — пессимистично SL) или fallback по горизонту в барах 1m (`2×15m → 30×1m`). Spot и futures — один путь (`market=`). UI: чекбокс **1m TP/SL**, спины TP/SL (%). Выкл. → старый выход по close основного ТФ. Старые opens без `exec_interval` тоже на main TF.

**HTF (зафиксировано, не сейчас):** третий ТФ только как **bias 4h** (не 6–8h и не третий вход): sync + фильтр soft-стороны по режиму; journal `htf=…`. После anti-horizon и веса меток по `pnl_usdt` (entry ✅). Пока — копим sized-опыт на dual TF + банк.

**Chat «анализ рынка»:** intent `market_situation` → срез банка / opens / свежих analysis из journal (`format_market_situation_block`). Вопрос «одна модель или per-ticker?» → `market_ml_scope` (MLP 24 фичи, общая policy).

**Session digest:** `.eurika/ml/session_seen.json` — при открытии Qt (`load_market_preferences`) в ленту Market блок «ПОКА ТЕБЯ НЕ БЫЛО» (fill/Σedge/ΣPnL$/выходы/equity Δ); Chat intent `session_digest` («пока меня не было») без сдвига last-seen.

**Chat-first (тонкий срез):** при старте Qt активна вкладка **Chat**; подвкладка **Агент** (бывш. Dialog); полоска режимов → Market / Models→ML; справа на Агенте панель **Контекст** (goal/pending/last run + **авто-Diff** + **Apply после Diff** + прыжки Terminal/Approvals); `chat_mode_status_label` зеркалит краткий статус paper. Автостарт Ollama **не** переключает на Models.

**Тайминг open/close:** при закрытии пишутся `mfe_pct` / `mae_pct` / `entry_timing_score`; entry-модель учит BUY/SELL только если `correct` **и** хороший тайминг (`mfe ≥ TP` или score > 0). **Вес сэмпла** в micro-train: `|pnl_usdt|` (иначе `|edge|`), clamp 0.25…8 — крупные $ влияют сильнее ровных correct. **Burst-fade:** `entry_setup_ok` режет SELL при +burst>2 / BUY при −burst<-2 **только** пока импульс не выдыхается (≥2 из rsi/macd/bb deltas против); после кульминации short/bounce разрешены. Exit-модель `market_exit.pt` (HOLD/CLOSE) на 1m-фичах; CLOSE с +MFE/giveback весят больше при train; может закрыть раньше при edge ≥¼ TP; при вооружённом MFE и отдаче — мягче bank (`should_model_exit` + `mfe_pct`). TP/SL/горизонт остаются жёстким safety. **Time-stop (anti-horizon):** после MFE ≥~0.28×TP, если ход отдан (≤40% MFE или ≤0) — выход `time_stop` до горизонта. Ретро-сэмплы → `.eurika/ml/exit_samples.jsonl` (+ `mfe_pct`/`giveback`). После model-exit — cooldown **20×1m**; после **SL — 40×1m** той же стороны.

**Уровни TP/SL/trail:** модель `market_levels.pt` учится по MFE/MAE закрытых сделок (учитель: TP≈0.85·MFE, SL≈1.15·MAE, trail≈0.35·MFE). При открытии: **model → эвристика(vol/burst) → UI**. Спины UI = мягкий потолок / запасной, не жёсткие уровни. В ленте: `TP=… [model|heuristic]`.

**Стиль входа (market/limit/stop/oco):** после закрытия на 1m-пути ретро-учитель выбирает стиль с лучшим fill vs signal → `.eurika/ml/style_samples.jsonl` → `market_style.pt`. В бою: **model → эвристика-bootstrap** (пока <8 style-меток). Soft-bias: близкий cancelable (`model/cancelable`); soft-entry → **oco** (`…/soft_bracket`). Fill одной pending-ноги отменяет siblings (`sibling_fill`); сигнал противной стороны снимает pending (`side_flip`, в т.ч. на том же main-баре). DCA — позже (после risk-caps).

### Paper entry types + trailing (цель обучения)

**Без live-ордеров.** Симуляция на 1m (spot+futures):

| Тип входа | Поведение |
|-----------|-----------|
| `market` | сразу по last close 1m |
| `limit` | ждём касания `limit_px`; отмена при invalidate / expire |
| `stop` | условный: касание `stop_px` → вход; иначе отмена |
| `oco` | limit + stop; первое исполнение отменяет второе |

**Отмена pending:** рынок ушёл против плана на `invalidate_pct` от `signal_px`, или истек `pending_horizon` (бары 1m) → запись `cancelled` (урок «не входить»).

**Выход:** TP / SL / горизонт / model-CLOSE + **trailing stop** (`trail_pct`: активируется только после хода ≥ trail в плюс; подтягивает SL за extreme, не ослабляет). `trail_extreme` в opens — кэш для UI / если entry-бар выпал из окна; при видимом entry симулятор всегда пересчитывает extreme с пути (иначе ложный trail на раннем баре).

Хранение: `.eurika/ml/pending_orders.json` + opens с `entry_style`, `trail_pct`, `trail_extreme`. Обучение: filled → как сейчас (+ style); cancelled → HOLD для entry; trail/TP/SL в `exit_reason`.

**Журнал Market:** каждая строка ленты дописывается в `.eurika/ml/market_journal.jsonl` (`ts`, `kind`, `message` + опционально `reason`, `bar_ts`, `symbol`, `market`, `edge`…). Очистка UI не стирает файл — пишется `журнал очищен`. **Ротация:** раз в 7 дней или при размере ≥16 MiB → `market_journal_YYYYMMDD_HHMMSS.jsonl` (хранятся 2 архива). Это только лента UI, **не** `paper_trades` / веса. Без секретов.

**Фичи (24, сырьё для ML, не торговые правила вроде «RSI низкий → buy»):** базовые `ret_1/4`, `ret_window`, `sma_ratio`, `volatility`, `hl_range`, `vol_z`, `atr_burst`, `range_break`, **`rsi_14`**, **`bb_pos`**, **`macd_hist`**; динамика `rsi_delta` / `bb_pos_delta` / `macd_hist_delta`; `bb_width`; структура `dist_to_low/high_{20,40,win}`; MA `sma_slope`, `price_vs_sma_slow`. Entry = MLP(`n→32→3`). Окно фич = 40 баров. При сильном всплеске горизонт paper `max(user_h, 4)`. Старые короткие `feature_vec` паддятся нулями; несовместимые Linear-веса → momentum до ретрейна. **PnL:** Σ `edge` (после fee) — всего / live / spot|fut / сессия с включения Live (`.eurika/ml/live_session.json`); плюс **USDT** (`pnl_usdt`, equity банка) в Models→ML и статус Market.

**Paper bank (фаза 1):** `.eurika/ml/paper_portfolio.json` — старт **1000 USDT**, риск **1% equity** как маржа на сделку, futures lev **1…5×** от confidence/side_prob (spot=1); **soft futures ≤2×** (UTC 07–09 → 1×) + tighter soft SL/trail; суммарная маржа ≤ **30% equity**, отказ входа → journal `hold` «нет бюджета риска». Journal open/pending пишет `utc_hour` (наблюдение 08:00). `pnl_usdt ≈ edge × notional` (убыток clamp к марже). Непрерывный банк (не сбрасывается при Live toggle). Фаза 2: ML-аллокация/плечо (частично), вес меток по `pnl_usdt` (entry ✅) / exit MFE-giveback ✅.

**Отложено (издержки futures):** сейчас фикс. `fee=0.001` (~0.1% round-trip) в `label_trade`. Нет: разных комиссий spot vs futures, **funding**, ликвидаций. Paper-плечо/маржа — есть (правила выше); ML-плечо и fee по рынку — позже.

Spot/Futures тикеры — **раздельные ручные списки** (`.eurika/ml/ticker_lists.json`); «Заполнить spot» — разово из балансов.

**Сброс исследования:** кнопка «Сброс счётчика» пишет `.eurika/ml/explore_baseline.json` (baseline = текущий total live). Cap считает только новые метки после сброса; `paper_trades` и веса не трогает.

---

## Связи

```
record_outcome (apply_stage)
    ├── memory.learning.append → EventLog (type=learn, result, output.failure_reason)
    └── append_learn_to_global (опционально)

get_recent_failures → EventLog (learn, result=False) — bounded view
get_merged_learning_stats → LearningView.aggregate_* + global_memory
```

---

## STM (краткосрочная память)

ExecutionContext — контекст текущего fix-cycle. Не сохраняется в LTM.

| Поле | Роль |
|------|------|
| snapshot_before/after, delta_score | Состояние до/после |
| current_goal | Текущая цель (опционально) |
| attempt_count | Попытки в сессии |
| session_failures | Провалы в сессии |

---

## Операционность pattern library

Pattern library (OSS hints в diff) полезна **только** когда learning loop реально меняет поведение. Иначе — статический каталог.

| Условие | Поведение |
|---------|-----------|
| success_rate < 0.25, total ≥ 3 | OSS hints = 0 (не усиливать провальные стратегии) |
| success_rate ≥ 0.25 или total < 3 | OSS hints до 3 (по умолчанию) |

**Реализация:** `build_hints_and_params(learning_stats=...)` → `_oss_hint_limit_for_smell_action`.

---

## Влияние памяти на planner

Planner читает enriched failures и меняет поведение (не только сортировку):

| Сигнал | Действие |
|--------|----------|
| `(kind, plan_hash)` в failed pairs | Deprioritize: ops в конец при повторе плана |
| `kind` failed 2+ раз (любой plan) | `apply_failure_based_fallback` → swap kind (напр. split_module → refactor_module) |
| `plan_hash` failed | Reverse ops order (стратегическая вариация) |

**Функции:** `get_recent_failed_kind_plan_pairs`, `get_kind_plan_failure_counts`, `apply_failure_based_fallback`, `sort_and_reindex_by_learning(failed_kind_plan_pairs=..., kind_plan_counts=...)`.

---

## Experience Memory с delta_energy (R9)

**Источник:** docs/archive/review.md §Experience Memory. Цель — опыт как `(action, delta_energy, risk, success)`.

| Атрибут | Текущее | Целевое (review) |
|---------|---------|------------------|
| **Запись** | `record_outcome(..., delta_energy=...)` → learn event output.delta_energy | ✅ apply_stage передаёт ctx.delta_score |
| **Хранение** | EventLog, type=learn, output.delta_energy | ✅ |
| **Weight update** | delta_energy (default), success_rate при `EURIKA_WEIGHT_ADAPTATION_DELTA_ENERGY=0` | W -= lr × delta_energy (P6) |
| **Опция** | `EURIKA_WEIGHT_ADAPTATION_DELTA_ENERGY=0` | success_rate heuristic вместо delta_energy |

**Текущий adapt:** `weight_store.adapt_weights_from_experience`. По умолчанию W -= lr × delta_energy (Energy-based loop). Обрабатывается только последнее событие с delta_energy.

---

## Known gaps (BOUNDED_EVOLUTION §5)

| Пробел | Идея | Когда |
|--------|------|------|
| Агрегаты без decay | age-based decay, recency weighting | при накоплении устаревших learning_stats |
| EventLog=500 | high-value events (learn/patch) приоритетнее scan | при потере контекста |

---

## Операционный контекст (trading)

- Рабочий торговый бот **не** в локальном `/mnt/.../binance` — на **`prodg.winex.org`** (`~/lbot`, SSH `Host prodg`).
- Eurika: read-only SSH probe `eurika.integrations.remote_lbot` + Binance API probe (ключи в `.env`). Управление ордерами / start-stop бота — вне текущей поверхности.

## Ссылки

- **archive/ARCHITECTURE_MEMORY_REVIEW.md** — исторический разбор памяти (SoT сейчас этот файл)
- **ROADMAP.md** §5.8 — STM/LTM маппинг
- **Architecture.md** §0.9 — Execution Model
- **archive/EXECUTION_MODEL_PLAN.md** — аудит стабильного ядра (выполнено)
- **BOUNDED_EVOLUTION.md** §5 — Risks (decay, high-value events), §7 — EnergyModel resource constraint
- **VISION.md** — продуктовая цель и ops-окно наблюдения

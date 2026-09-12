# Eurika — продуктовое видение

> **Роль документа:** долгосрочная цель и продуктовые границы. Текущий план
> разработки ведётся в [DEVELOPMENT.md](DEVELOPMENT.md); подробная история и
> расширенный backlog — в [ROADMAP.md](ROADMAP.md).

**Одна фраза (продукт сейчас):** Cursor-подобная оболочка для работы с кодом и агентом, плюс самообучение и paper-торговля как режимы того же продукта — не отдельные приложения.

**Главная цель (master):** постепенно превратить Eurika из статического анализатора кода в **саморазвивающуюся интеллектуальную инженерную систему** — наблюдать себя, анализировать состояние, исследовать внешнюю информацию, формировать гипотезы, предлагать улучшения, проверять их экспериментально и помогать человеку создавать и развивать другие проекты. Не иллюзия сознания, а **инженерно управляемая** автономия: измеримые механизмы самонаблюдения и самоулучшения.

**Северная звезда ценности:** ты строишь **скелет** (данные, метки, банк, verify, journal, HITL); Eurika **сама учится** давать измеримую ценность — успешные coding outcomes / paper equity — из опыта (`.eurika/events.json`, `.eurika/ml/`), не из ручных правил «RSI→buy».

**Единица прогресса:** не число фич, а способность **самостоятельно обнаруживать, объяснять, проверять и исправлять собственные ограничения** (с HITL на опасных действиях). Каждый новый модуль обязан отвечать: *какую измеримую способность он добавляет?* Ответ «так будет умнее» — модуль не создавать.

## Master: цикл саморазвития

```text
OBSERVE → UNDERSTAND → MODEL → RESEARCH → REASON → PROPOSE
  → PLAN → VERIFY → ACT → MEASURE → LEARN → MEMORIZE → OBSERVE AGAIN
```

Reasoning **предлагает**; Policy/Safety **разрешает**; Executor делает **только разрешённое**. Граница: Observation / Reasoning / Proposal / Authorization / Execution / Verification — не смешивать. Автоapply потенциально опасных действий запрещён.

**Целевой проход (инженерное саморазвитие):**
наблюдаю себя → понимаю состояние → нахожу проблему → ищу решения (источники / AI-консультанты) → гипотеза → план → безопасный эксперимент → измеряю → accept/reject → сохраняю опыт → обновляю модель себя → следующая возможность.

Поколения: `v0.1 → анализ → ограничения → proposal → verify → v0.2 → …` — механизм, которым Eurika **создаёт следующую версию себя**, а не «конечная Eurika сразу».

### Принципы доказательности

Утверждение по возможности: источник · наблюдение · доказательство · уверенность · проверяемость · история. Разрешены ответы «не знаю» / «недостаточно данных». Не выдумывать знания, исходы экспериментов и успешность своих правок. Гипотеза ≠ факт. Улучшение — только измерениями, не самооценкой «я стала умнее».

### Архитектурные уровни (целевая схема)

Self / World / User models → Knowledge → Reasoning → Planning → Policy → Action → Verification → Memory → Learning.

Первое крупное расширение ядра (не новый автономный агент): **Self Model + Capability Model + Goal Model**.

### Этапы и карта к существующему ядру

| Stage | Смысл | Уже есть / частично | Пробел |
|-------|--------|---------------------|--------|
| **0 Observer** | scan · analyze · measure · report · remember | scan/doctor/graph/smells, EventLog, journal, live_activity; **Self Model v0/v2** (`.eurika/self_model.json`: **deps / versions / problems** first-class; Chat «модель себя», CLI `self-model`) | более глубокий inventory runtime-пакетов |
| **1 Architect** | architecture · history · diff · trends · recommendations | project graph, smells, CYCLE_REPORT, Architecture Freeze | тренды/регрессии архитектуры как first-class |
| **2 Researcher** | web · sources · KB · external AI consultant | web_search в bug-hunt, `learn-github` / pattern_library, multi-model chat | сравнение нескольких AI + evidence-store с confidence |
| **3 Reasoner** | hypotheses · planning · decisions | planner, goals/reflection v1, chat interpreter; **Goal Model v0**; **Hypothesis Engine v0**; **multi-hypothesis ranking v0**; **planning / planner-core coupling v0**; **critic/decision coupling v0** + **multi-role critic v0** (роли evidence/verify/hypothesis/self — алгоритмические голоса, не лишние LLM-агенты; soft escalate allow→review) | Stage 6 earn |
| **4 Experimenter** | sandbox · A/B · rollback | polygon, prove-cycle, propose+sandbox, worktree; **Experiment Memory v0**; **Formal A/B v0/v2** (core + suite: modules/density/max_blast/**layer_violations**; CLI `ab-compare` / Chat «a/b»; **не** autoapply); **A/B rescan auto** | walk-forward / multi-trial suites |
| **5 Self-improving** | controlled self-mod · anti-regression | C.14 HITL, idle self-dev, bug-hunt → Approvals; caps BOUNDED_EVOLUTION; Capability + HITL metrics; Formal A/B v2; **multi-role critic v0**; Self Model first-class deps/versions/problems; A/B rescan-when-stable; multi-hypothesis ranking | Stage 6 earn |
| **6 General engineering** | host assist · projects · domains · finance/earn | Chat host tools (HITL/sudo), coding shell, paper Market; **Project Creation pipeline v0** + **scaffolds** (`minimal` / `python` / `python-cli` поверх `eurika init` / «создай проект … как python»); **host admin read-only v0** | earn вне paper-лабы |

**Не делать преждевременно:** fake consciousness; бесконечный autonomous loop; полный доступ к ОС; silent rewrite production; multi-agent «ради агентов»; LLM там, где хватает алгоритма; сложная память без потребителя; оптимизация без измерения.

**Safe self-modification (канон = текущий C.14):** propose → backup/isolated workspace → modify → tests/static/arch → compare baseline → accept/reject (HITL). Никогда не подменять рабочую версию напрямую. Детали ритуала: [BOUNDED_EVOLUTION.md](BOUNDED_EVOLUTION.md) §8, ROADMAP §4.6.

**Память (целевые слои vs сейчас):** Working / Episodic / Semantic / Procedural / Architectural / Experiment / KB. Сейчас: `.eurika/events.json`, dialog/goals, pattern_library, ml journal, pending_plan — различать fact / observation / hypothesis / decision / experiment / result / lesson при наращивании, не смешивать.

**Домены позже (не сейчас в окне):** richer host admin (не полный доступ к ОС — mutating уже HITL v0), vision/screen как наблюдения, engineering domains, financial intelligence с uncertainty, Ability to Earn (problem→MVP→measure) — Market paper остаётся **экзамен политики**, не live-деньги.

### Политика хардкода (Chat / Agent)

- **Запрещено** вручную растить доменные request/response-листы (bluetooth / GPU / «посмотри что у меня» / …) — это не продукт, это костыль.
- **Хардкод-листы допустимы только** если Eurika **сама** их составляет и обновляет из опыта (feedback, outcomes, journal, удачные tool-turns) — человек задаёт скелет обучения, не словарь фраз.
- **Исключение (скелет, не знание домена):** HITL (`применяй`), диалог sudo/пароля для host tools, узкие project-facts (`ls`/`scan`) — пока без самописных phrase-books. Binary allowlist для chat host tools снят: команды из `eurika-cmds` выполняются, привилегии — через UI.
- **Цель Chat:** **LLM-first** → tools (shell / сеть / пакеты ОС / Cursor) → LLM; маршрутизация и «что спросить/ответить» со временем — из `.eurika/` опыта, не из новых `if "колонка" in msg`. На любой запрос (хост, принтер, цена, код) Eurika сама выбирает средства; sudo и правки репозитория — через UI/HITL, не тихий rewrite.

### Политика выбора технологий

- Eurika не привязана к одному языку: язык выбирается по корректности, скорости,
  доступным библиотекам и стоимости сопровождения.
- Python остаётся для agent/ML/Market/orchestration, TypeScript — для IDE-клиентов.
  Rust/C/C++ допустимы для доказанных горячих участков (индекс, поиск, watcher,
  parsing/diff, PTY), но только после профилирования и с contract-тестами на границе.
- Не переписывать рабочие подсистемы «ради быстрого языка»: сначала измерить
  bottleneck, затем заменить минимальный участок за стабильным API.

## Три слоя

1. **Shell (как Cursor)** — chat-first: агент в центре; проект, diff/apply, terminal, модели — вокруг. Вкладки Dashboard/Graph/Commands — вторичные панели, не главный экран.
2. **Agent + Learn** — scan → plan → apply → verify → `record_outcome`; опыт в `.eurika/events.json` переживает рестарт и меняет следующий план.
3. **Market (paper only)** — Live paper Binance → метки → MLP entry/exit/levels/style в `.eurika/ml/`. Без live-ордеров. В UX это режим Chat→Market / skill агента, не «торговое приложение рядом».

**Binance как инструмент, не мозг (2026-09-11):** Market-ИИ Эврики — **свой** (paper journal → головы в `.eurika/ml/`). Binance Agent OS / MCP (`https://agent.binance.com/mcp/agentic`) подключается как **внешний tool** рядом с Web/GitHub: `eurika/integrations/binance_mcp.py` — handshake + `tools/list` + `tools/call` **только read-only** (market data / balances). Имена вида `*order*`, `*cancel*`, `*transfer*`, `*convert*`, `*withdraw*` блокируются политикой (`policy_blocked`) независимо от выданных scopes. CLI `eurika ml-market mcp .` / Chat «binance mcp». Live-исполнение — только после снятия Market freeze и отдельного HITL-контура (proposal → approve → order), не из reasoning напрямую.

## Сейчас (paper = лаборатория обучения)

**Принцип:** реальных ордеров нет. Вся paper-торговля существует, чтобы **научить Эврику** находить прибыльные входы/выходы. Бумажный банк — не цель, а экзамен: «умеет ли текущая политика зарабатывать, когда платит комиссию». Всё остальное (отклонённые воротами входы, исследование при HOLD) — домашняя работа через тени: метки без риска для equity.

### Стоимостные ворота входа

С **2026-08-07** — разбор первой недели (2026-07-31…08-07, 1956 закрытий, equity 1000 → 987.55):

- Сигнал **есть**: направленный доход до издержек +0.0335%/сделку, t=2.67, ДИ [+0.009; +0.058]%.
- Комиссия **0.0892%/сделку** — в 2.7× больше эджа. Валовый PnL +3.24 $, комиссии −19.56 $ → нетто −12.45 $. Оборот 21 519 $ на банке 1000 $ за 6.6 дней.
- Ужесточение SL **не помогает**: убыточные идут против сразу (медианный MFE у SL 0.095% при TP 1%), симуляция SL 0.3% даёт −9.56 $.
- Эдж живёт только там, где **ход расширяется**: верхний квинтиль `atr_burst` +0.098%, `vol_z` +0.113% против ~0.02% в остальных.

Отсюда **стоимостные ворота** (`eurika/ml/entry_cost.py`): вход открываем, только если ожидаемый эдж покрывает комиссию с запасом `cost_mult` (1.5). Скелет — арифметика «эдж ≥ ×комиссии»; порог **калибруется** из `paper_trades.jsonl` вместе с обучением голов и лежит в `weights/entry_cost_gate.json` (не магическое число в коде). Мера расширения — `min(vol_z, atr_burst)`. Explore воротам не подчиняется: он покупает метки осознанно.

### Теневые входы: скорость обучения отвязана от скорости торговли

Ворота режут поток сделок в ~7 раз, и наивно это резало бы **обучение** во столько же раз — а задача не «торговать поменьше», а научиться отличать удачный вход. Хуже того, фильтр цензурирует выборку: в журнал попадают только те режимы, что ворота пропустили, и Эврика перестаёт видеть, чем кончаются входы, которые она отвергла.

Отсюда **теневые входы** (`shadow_open.json`): и отклонённый воротами вход, и explore при HOLD записываются и доводятся до конца **тем же** кодом разрешения (TP/SL/trail/time-stop/model-exit), но не трогают ни equity, ни маржу, ни cooldown, ни ленту journal. В `paper_trades.jsonl` — `shadow: true`, `live: false`, `pnl_usdt: null`. Головы учатся на реальных **и** теневых строках; деньги и live-статистика — только по реальным (экзамен под воротами). Explore больше не «жжёт» банк ради меток.

Итог: в банк идут только входы, которые должны окупать комиссию; **учимся** на полном потоке (ворота + explore-тени).

### Почему ворота не открывают себя сами

Первая версия калибровки сравнивала средний эдж всего «хвоста» выше порога с комиссией. Под цензурой это ломается: через неделю в журнале остаются только пропущенные сделки, любой более низкий порог даёт тот же самый хвост, правило решает «платит всё» и **сбрасывает порог в минимум** — проверено на реальных данных, порог 0.25 → −3.0. Дальше колебание с периодом в неделю.

Сейчас порог обязан оправдаться на **той полосе, которую он впускает** (`BAND_WIDTH` 0.5), а не только на хвосте: полоса должна и сама окупать комиссию, и содержать ≥40 наблюдений. Нет данных о полосе — ворота не опускаются. Поставщик этих данных — теневые входы, поэтому две правки работают только вместе.

Проверка вперёд (правило калибруется на 08-01…08-04, дни 08-05…08-07 при этом не видны): правило выбирает порог 0.75 → без ворот 965 сделок и **−6.90 $**, с воротами 55 сделок, валовый эдж +0.209% (t=3.02), **+0.50 $**. На всей неделе правило выбирает 0.5. Обучаемый предиктор эджа по всем 24 фичам, наоборот, out-of-sample не работает (ранговая корреляция +0.011) — поэтому ворота держатся на двумерной мере расширения, а не на регрессии.

Известная асимметрия: ~~тень входила по рынку, живая книга в 97% через OCO~~ — снято 2026-08-08 (B12: shadow pending/OCO). Честный учёт комиссий также включён (B13): каждая исполненная сторона платит maker/taker ставку.

Смотреть в journal: `отклонён — ход не окупает комиссию`, строку `стоимостные ворота` в learn-событиях, сделок в день (ожидаем ~40 вместо ~285) и **нетто-эдж на сделку**, а не win rate.

С **2026-08-02**: при explore off модель часто залипала в HOLD (~0.52/0.25/0.23) → **0 сделок**. Включено:

1. **Soft entry** — если argmax HOLD, но HOLD<0.55 и сторона ≥0.24 с зазором → BUY/SELL (`model/soft`) + фильтр сетапа (не входить у противоположной границы окна).
2. **Exit-first** — model-CLOSE с **¼ TP** (было ½); soft CLOSE-prob; bank при CLOSE>HOLD (~0.30×TP); trail ×0.75 при открытии; MFE-fade bank раньше.
3. **Reentry cooldown** — после model-exit блок той же стороны **20×1m**; после **SL — 40×1m** (`reentry_cooldown.json`); противная сторона свободна.
4. **Cancelable entry bias** — близкий cancelable вместо market; soft-entry → **OCO bracket** (limit+stop); fill одной ноги → `sibling_fill` / OCO cancel; смена стороны → `side_flip` pending.
5. **Paper bank 1000 USDT** — риск 1% equity на сделку (маржа); **soft entry → ×0.6 маржи** (`soft_sz×0.6`); futures lev 1…5× = **уверенность** модели (side prob); **soft futures ≤2×** (в UTC 07–09 → 1×); soft futures SL/trail ужесточены; суммарная маржа ≤30% equity; PnL USDT = edge×notional → рост `equity_usdt`.
6. **Anti-horizon (time-stop)** — MFE ≥~0.28×TP и ход отдан (осталось ≤40% MFE или ≤0) после min баров → выход `time_stop` до мёртвого горизонта.
7. **Exit train** — CLOSE-сэмплы с +MFE/giveback весят больше (`sample_weight=close_mfe|giveback`).
8. **UTC hour tag** — journal `utc_hour` на open/pending (наблюдение часа 08:00; мягкий soft-cap в 07–09).

Следить journal: `model/soft`, `стиль=oco`, `side_flip`, `sibling_fill`, cooldown (model/SL), `time_stop`, `lev soft_cap` / `lev conf`, `soft_sz×`, `utc=`, setup-reject, отказ «нет бюджета риска»; **equity / PnL$** vs доля `horizon`/`sl`/`model`/`time_stop`.

**Режим сейчас:** Live с банком + time-stop + soft futures risk + soft size-cap + SL-cooldown. Не сбрасывать банк без причины.

### Ежедневный разбор journal (5 минут)

Файлы: `.eurika/ml/market_journal.jsonl`, `paper_trades.jsonl`, `open_paper.json`, `shadow_open.json`, `paper_portfolio.json`, `weights/meta.json`, `weights/entry_cost_gate.json`.

1. Market root всё ещё `.Qt`? (`EURIKA_MARKET_ROOT` или source-root из
   `eurika.ml.root`; выбранный coding-workspace на него не влияет)
2. Equity / Δ USDT; новые закрытия: edge, `pnl_usdt`, `exit_reason`, source (`model` / soft / explore)
3. Доля HOLD vs сделок; не залип ли только HOLD; много ли `horizon`/`sl` vs `model`
4. Ошибки sync / QThread / «Live paper выключен» без причины
5. Открытые paper и pending — нет ли зависших; legacy opens без margin → дождаться закрытия
6. **Экономика:** валовый PnL vs сумма комиссий; нетто-эдж на сделку; сколько входов отсеяли ворота и какой порог выбрала калибровка
7. **Обучение:** строк `shadow: true` за сутки (должно быть в разы больше реальных — иначе поток меток пересох); не растёт ли `shadow_open.json` монотонно (значит тени зависают, а не разрешаются); эдж теней ниже порога — если он стабильно окупает комиссию, ворота откроются сами, и это ожидаемо
8. **Якорь экзамена 2026-08-24 → разбор 2026-08-31:** см. [MEMORY.md](MEMORY.md) § «Якорь экзамена» и `.eurika/ml/exam_checkpoint.json`. Сверить `covers_cost` / `expected_edge`, rolling last 200 live, equity Δ. Если ворота всё ещё `covers_cost: нет` и last 200 в минусе — разбор ворот/комиссии по journal, **не** новый entry / explore on / HTF.

Считать честно: `edge` уже за вычетом комиссии, поэтому «win rate 62%» ничего не значит без отношения средней прибыли к среднему убытку (на неделе 1:2.15 → безубыток требует 68.2%).

## Продуктовый горизонт после окна (не порядок разработки)

### A. Продукт / UX
1. ~~**Chat-first coding-оболочка**~~ ✅ (2026-08-09, standalone MVP): основным coding UI становится самостоятельный `eurika-desktop/` (Electron + Monaco + xterm); расширение VS Code/VSCodium `vscode-extension/` — optional adapter. Оба клиента используют общий `clients/eurika-client` и Python backend `eurika.agent` по versioned streaming JSON-RPC/stdio. Proposal/Apply/Reject, stale checks, checkpoints и persistent Chat history принадлежат ядру, а не VS Code. Desktop уже показывает Chat/Diff/Approvals/Commands/Market/**Models**; **parity v2 (2026-09-11):** Commands observer + `reviewInApprovals` + host-admin Context + Desktop `chat/send` / `@` / `project/create`. **Models-tab v0 (2026-09-12):** `panel/state models` + `models/prefs` (routing, без ключей и без Ollama process mgmt). Qt остаётся. Release/eval gate: `docs/LOCAL_CODING_AGENT_RELEASE.md`.
2. ~~**Session digest «пока тебя не было»**~~ ✅ (2026-08-03) — при открытии Qt в ленту Market; Chat: «пока меня не было».

### B. Market paper (по статистике journal)
3. ~~**Anti-horizon / time-stop**~~ ✅ + усиление 2026-08-03 (arm ~0.28×TP, keep ≤40%, min bars↓).
4. ~~**Вес меток по `pnl_usdt` / edge**~~ ✅ — entry MLP; exit CLOSE weighted by MFE/giveback ✅.
5. ~~**Exit / burst-fade**~~ ✅ — SELL при +burst>2 ок **после** fade; model-exit банчит отдачу MFE раньше.
6. **HTF bias 4h** (не 6–8h): только **фильтр режима** — sync 4h + 2–3 фичи (`ret`/`sma_ratio`/знак тренда); soft BUY/SELL лишь если HTF не против; journal `htf=up|down|flat`. **Не** третий боевой вход и не TP на 4h. 6–8h — мало баров для учёбы; 4h предпочтительнее. **Не трогать**, пока SL/horizon не стабилизируются.
7. ~~**ML risk / аллокация**~~ частично ✅ — futures lev = confidence; soft futures ≤2× (UTC 07–09 → 1×) + tighter SL/trail; **soft margin ×0.6** (`soft_sz×`); risk-головы — позже.
8. ~~**Комиссии spot vs futures** / funding~~ ✅ — с 2026-08-08 комиссия считается **по каждой стороне**: spot maker/taker 0.1% + 0.1%; futures maker 0.02%, taker 0.05%; TP считается maker, market/stop/SL/model/time — taker. Funding с Binance public `premiumIndex`/`fundingRate` (signed; иначе 0). Funding-farm — отдельный режим.
9. ~~**Структурный journal**~~ ✅ — `reason`, `bar_ts`, `symbol`, `market`, `utc_hour` (+ edge/correct у outcome).
10. ~~**Стоимостные ворота входа**~~ ✅ (2026-08-07) — `entry_cost.py`, порог калибруется из журнала, проверен вперёд на 08-05…08-07.
11. ~~**Теневые входы + защита калибровки от самораскрытия**~~ ✅ (2026-08-07) — `shadow_open.json`, обучение на отклонённых входах; порог оправдывается на впускаемой полосе; **explore тоже тень** (банк = экзамен политики, не костёр меток).
12. ~~**Тень должна входить как живая книга**~~ ✅ (2026-08-08) — shadow pending/OCO в `pending_orders.json` с `shadow: true`; fill → `shadow_open`; cancel-метки `live: false`; live и тень не гасят друг друга через `sibling_fill` / side_flip / margin.
13. ~~**Честный учёт комиссий**~~ ✅ (2026-08-08) — `fee = entry_fee + exit_fee`; entry liquidity берётся из `fill_leg` (`limit` maker, `stop/market` taker), TP — maker, остальные выходы — taker; breakdown пишется в trades и structured journal; exit train/serve одинаково оценивают модельный CLOSE как taker. Legacy rows с прежними 0.1%/0.08% корректно переоцениваются при калибровке ворот без переписывания журнала.
14. ~~**Зависшие открытые позиции**~~ ✅ (2026-08-07) — причина: `find_entry_index` при входе старше окна 1m ставил индекс 0 → горизонт никогда не истекал. Фикс: scrolled-out → −1; страховка `max_age` (N×горизонт, N=3) / `stale` (вход выпал из окна после planned hold); `DEFAULT_EXEC_MAX_KEEP` 360.
15. **Метки всё ещё частично свои же** — политика входа учится на исходах, отобранных `soft_entry`; теневые входы снимают цензуру ворот, но не эту. Мера: доля меток, пришедших не от собственного решения.
16. Позже: walk-forward; impulse-путь на 1m-фичах при сильном burst/break; полный режимный фильтр по часу (сейчас тег + soft-cap 07–09).
17. **Аудит технических признаков, не indicator-rules:** после стабилизации журнала провести ablation/walk-forward для RSI/MACD/SMA/Bollinger/volume и их динамики, оценивая только прирост out-of-sample net edge после комиссий. При необходимости добавить нормированный stochastic `%K` как непрерывный признак положения в диапазоне — только если он даёт независимый прирост относительно уже имеющихся `dist_to_low/high`; не вводить правила вида `RSI < 30 → BUY` или «выход за Bollinger → возврат».
18. ~~**Ворота калибруются по активному рынку**~~ ✅ (2026-08-17) — комиссия круга у спота 0.2000% против 0.0948% у фьючерсов, а `calibrate_cost_gate` усредняла обе площадки: порог требовал 0.184% эджа вместо фьючерсных 0.139% и вставал на +2.00. Теперь `markets=` ограничивает выборку теми площадками, где реально идёт торговля (`live_paper` передаёт активные `market_kinds`), а `retained_previous`-защита придерживает только **ужесточение**: смягчение уже обязано доказать свою впускаемую полосу, и блокировать его значило заморозить ворота на достигнутой строгости. На данных 08-17: `both` → +2.00 (без изменений), `futures` → **+0.50** (хвост 350 против 82, эдж 0.179% против нужных 0.139%), `spot` → свою комиссию не окупает ни на одном пороге. Область калибровки пишется в `entry_cost_gate.json` (`markets`) и в journal-строку ворот.
19. **Обучение голов остаётся общим по рынкам** — `train_market_policy` / `levels` / `style` берут весь журнал без фильтра, спот это 35.5% исполненных строк. Направление на споте не шум (BTC ходит одинаково), но `edge` там систематически хуже на комиссию, и веса меток по `|pnl|` учат «сетап плохой» вместо «площадка дорогая». Мерить долю спот-строк в пуле; фильтровать только если futures-only статистика покажет расхождение — пул с 3987 до 2574 резать вслепую нельзя.

### C. Agent / платформа
11. ~~**Plugin hooks** `after_*`~~ ✅ (2026-08-08, v1) — versioned JSON-safe immutable `HookContext`; canonical `after_scan/plan/apply/verify` (не CLI/Qt wrappers); конфиг `.eurika/plugins.toml` / `pyproject`; ordered + dedupe + fail-open; результаты в `report.plugin_hooks` и `.eurika/events.json`. Trusted in-process plugins, не sandbox.
12. ~~**Telegram-канал**~~ частично ✅ (2026-09-04…06, v1+) — `eurika telegram-bot` + Chat «запусти/останови/бот жив?»; allowlist; **push** Approvals + **/approve**/**/reject**; **push итога apply-approved**; решение из Telegram **зеркалится в Chat/Goals** Qt/Desktop; apply на диск только Qt/Desktop/`eurika fix . --apply-approved`.
13. ~~**Goals / reflection / nudges (v1)**~~ частично ✅ — status/reflection/clear + nudge; reject/apply отпускают sticky goal; «какая цель?» показывает последний итог после release; idle C.14 пишет `last_execution` + Approvals в панели Контекст (Qt/Desktop).
14. ~~**Саморазвитие через полигон (HITL)**~~ частично ✅ (ритуал v1 + **v1.5 bug-hunt**) — `eurika prove-cycle . --propose [--drill …] [--sandbox]` → Approvals → `eurika fix . --apply-approved`. **Bug-hunt:** `eurika bug-hunt . --propose [--sandbox] [--web]` — один реальный smell (не polygon) → sandbox → Approvals; anti-repeat recent target|kind (`.eurika/bug_hunt.json`); Chat «найди баг» / «предложи улучшение кода». **OSS learning:** Chat «обнови паттерны» / Desktop Commands `learn-github` → `pattern_library` для hints. **Idle:** ротация `… → llm_extract → bug_hunt`; anti-tread по `drill_ok`; apply только HITL. Desktop RPC: `idle-self-dev/prefs|run|status`. **Self+Capability+Goal v0:** `eurika self-model .` / Chat «модель себя» → `.eurika/self_model.json` + блок в Контексте. **HITL accept-rate + Experiment Memory v0:** `.eurika/hitl_journal.json` + `.eurika/experiments.json` (propose→decide→apply). **Hypothesis Engine v0:** `eurika hypotheses .` / Chat «гипотезы» → `.eurika/hypotheses.json` (evidence+expected; open/supported/refuted/insufficient). **Self-improvement metrics v0:** apply_ok_rate / verify_by_kind / time_to_decide / hypotheses_supported в snapshot + `self_improvement` journal. **Formal A/B v0/v2:** после sandbox smoke — baseline vs treatment (core + suite/`layer_violations`) → `.eurika/ab_trials.json` + `metrics.ab_v0`; CLI `ab-compare` / Chat «a/b»; не autoapply. **Planner-core coupling v0:** A/B + verify_by_kind + hypotheses soft-reorder ops в `fix`/prepare (не только bug-hunt). **Critic/decision coupling v0 + multi-role critic v0:** роли evidence/verify/hypothesis/self (алгоритм, не LLM-агенты) soft escalate allow→review. **Self Model v2:** first-class `deps` / `versions` / `problems`. Детали: [ROADMAP.md](ROADMAP.md) §4.6, [BOUNDED_EVOLUTION.md](BOUNDED_EVOLUTION.md) §8.

### Не брать
Live-ордера / ключи / freqtrade с prodg; indicator-правила «RSI→buy» / «памп→buy» как ML-логика; OPT/aviation/vpn как домен; третий ТФ как отдельный торговый движок; **Binance AI / MCP как решающий контур** («дай агенту scopes и пусть торгует») — MCP только read-only tool, решения остаются у Eurika + HITL.

## Не сейчас

Новые алгоритмы входа, explore on ради меток, HTF в коде до стабилизации equity, live-биржевые ордера, большой рефактор вкладок «ради красоты» без chat-first ядра; **silent** self-rewriting / онлайн-патчинг живого ядра без proposal+approve (полигон→HITL — можно, см. C.14).

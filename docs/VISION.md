# Eurika — продуктовое видение

**Одна фраза:** Cursor-подобная оболочка для работы с кодом и агентом, плюс самообучение и paper-торговля как режимы того же продукта — не отдельные приложения.

**Северная звезда:** ты строишь **скелет** (данные, метки, банк, verify, journal); Eurika **сама учится зарабатывать** — сначала измеримую ценность (paper equity / успешные outcomes), не обязательно только Binance. Политики и пороги — рычаги скелета; «как именно зарабатывать» должно вытекать из опыта (`.eurika/events.json`, `.eurika/ml/`), а не из ручных правил «RSI→buy».

## Три слоя

1. **Shell (как Cursor)** — chat-first: агент в центре; проект, diff/apply, terminal, модели — вокруг. Вкладки Dashboard/Graph/Commands — вторичные панели, не главный экран.
2. **Agent + Learn** — scan → plan → apply → verify → `record_outcome`; опыт в `.eurika/events.json` переживает рестарт и меняет следующий план.
3. **Market (paper only)** — Live paper Binance → метки → MLP entry/exit/levels/style в `.eurika/ml/`. Без live-ордеров. В UX это режим Chat→Market / skill агента, не «торговое приложение рядом».

## Сейчас (прибыль / soft-entry)

С **2026-08-02**: при explore off модель часто залипала в HOLD (~0.52/0.25/0.23) → **0 сделок**. Включено:

1. **Soft entry** — если argmax HOLD, но HOLD<0.55 и сторона ≥0.24 с зазором → BUY/SELL (`model/soft`) + фильтр сетапа (не входить у противоположной границы окна).
2. **Exit-first** — model-CLOSE с **¼ TP** (было ½); soft CLOSE-prob; bank при CLOSE>HOLD (~0.30×TP); trail ×0.75 при открытии; MFE-fade bank раньше.
3. **Reentry cooldown** — после model-exit блок той же стороны **20×1m**; после **SL — 40×1m** (`reentry_cooldown.json`); противная сторона свободна.
4. **Cancelable entry bias** — близкий cancelable вместо market; soft-entry → **OCO bracket** (limit+stop); fill одной ноги → `sibling_fill` / OCO cancel; смена стороны → `side_flip` pending.
5. **Paper bank 1000 USDT** — риск 1% equity на сделку (маржа); futures lev 1…5× = **уверенность** модели (side prob); **soft futures ≤2×** (в UTC 07–09 → 1×); soft futures SL/trail ужесточены; суммарная маржа ≤30% equity; PnL USDT = edge×notional → рост `equity_usdt`.
6. **Anti-horizon (time-stop)** — MFE ≥~0.28×TP и ход отдан (осталось ≤40% MFE или ≤0) после min баров → выход `time_stop` до мёртвого горизонта.
7. **Exit train** — CLOSE-сэмплы с +MFE/giveback весят больше (`sample_weight=close_mfe|giveback`).
8. **UTC hour tag** — journal `utc_hour` на open/pending (наблюдение часа 08:00; мягкий soft-cap в 07–09).

Следить journal: `model/soft`, `стиль=oco`, `side_flip`, `sibling_fill`, cooldown (model/SL), `time_stop`, `lev soft_cap` / `lev conf`, `utc=`, setup-reject, отказ «нет бюджета риска»; **equity / PnL$** vs доля `horizon`/`sl`/`model`/`time_stop`.

**Режим сейчас:** Live с банком + time-stop + soft futures risk + SL-cooldown. Не сбрасывать банк без причины.

### Ежедневный разбор journal (5 минут)

Файлы: `.eurika/ml/market_journal.jsonl`, `paper_trades.jsonl`, `open_paper.json`, `paper_portfolio.json`, `weights/meta.json`.

1. Live всё ещё на `.Qt`? (`~/.eurika/qt_settings.json` → `project_root`)
2. Equity / Δ USDT; новые закрытия: edge, `pnl_usdt`, `exit_reason`, source (`model` / soft / explore)
3. Доля HOLD vs сделок; не залип ли только HOLD; много ли `horizon`/`sl` vs `model`
4. Ошибки sync / QThread / «Live paper выключен» без причины
5. Открытые paper и pending — нет ли зависших; legacy opens без margin → дождаться закрытия

## Backlog после окна (порядок)

### A. Продукт / UX
1. **Chat-first оболочка** — частично ✅ (2026-08-03): Chat первая вкладка; подвкладка **Агент**; полоска режимов Агент/Market/Обучение + статус Market. Дальше: панели вокруг агента (без большого рефактора «ради красоты»).
2. ~~**Session digest «пока тебя не было»**~~ ✅ (2026-08-03) — при открытии Qt в ленту Market; Chat: «пока меня не было».

### B. Market paper (по статистике journal)
3. ~~**Anti-horizon / time-stop**~~ ✅ + усиление 2026-08-03 (arm ~0.28×TP, keep ≤40%, min bars↓).
4. ~~**Вес меток по `pnl_usdt` / edge**~~ ✅ — entry MLP; exit CLOSE weighted by MFE/giveback ✅.
5. ~~**Exit / burst-fade**~~ ✅ — SELL при +burst>2 ок **после** fade; model-exit банчит отдачу MFE раньше.
6. **HTF bias 4h** (не 6–8h): только **фильтр режима** — sync 4h + 2–3 фичи (`ret`/`sma_ratio`/знак тренда); soft BUY/SELL лишь если HTF не против; journal `htf=up|down|flat`. **Не** третий боевой вход и не TP на 4h. 6–8h — мало баров для учёбы; 4h предпочтительнее. **Не трогать**, пока SL/horizon не стабилизируются.
7. ~~**ML risk / аллокация**~~ частично ✅ — futures lev = confidence; soft futures ≤2× (UTC 07–09 → 1×) + tighter SL/trail; risk-головы — позже.
8. ~~**Комиссии spot vs futures** / funding~~ ✅ — spot 0.1% RT, futures 0.08% RT; funding с Binance public `premiumIndex`/`fundingRate` (signed; иначе 0). Funding-farm — отдельный режим.
9. ~~**Структурный journal**~~ ✅ — `reason`, `bar_ts`, `symbol`, `market`, `utc_hour` (+ edge/correct у outcome).
10. Позже: walk-forward; impulse-путь на 1m-фичах при сильном burst/break; полный режимный фильтр по часу (сейчас тег + soft-cap 07–09).

### C. Agent / платформа
11. **Plugin hooks** `after_*` — `routeCRM/plugins` + R5.
12. **Telegram-канал** к тому же агенту (`eurika` v1 `telegram_bot`).
13. Goals / reflection / nudges (v1) — после chat-first.

### Не брать
Live-ордера / ключи / freqtrade с prodg; indicator-правила «RSI→buy» / «памп→buy» как ML-логика; OPT/aviation/vpn как домен; третий ТФ как отдельный торговый движок.

## Не сейчас

Новые алгоритмы входа, explore on ради меток, HTF в коде до стабилизации equity, live-биржевые ордера, большой рефактор вкладок «ради красоты» без chat-first ядра.

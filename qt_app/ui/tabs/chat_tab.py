"""Chat tab: Dialog + Market sub-tabs (clean separation)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from qt_app.ui.main_window_helpers import ChatInputEdit
from qt_app.ui.scroll import VerticalScrollArea
from qt_app.ui.styles import SPIN_MAX_WIDTH, TAB_MARGINS, get_secondary_hint

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_chat_tab(main: MainWindow) -> None:
    """Build Chat with Agent (LLM) and Market (live paper) sub-tabs."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(*TAB_MARGINS)
    layout.setSpacing(4)

    inner = QTabWidget()
    main.chat_inner_tabs = inner
    main.chat_dialog_subtab_index = inner.addTab(_build_dialog_page(main), "Агент")
    main.chat_market_subtab_index = inner.addTab(_build_market_page(main), "Market")
    layout.addWidget(inner, 1)

    main.chat_tab_index = main.tabs.addTab(tab, "Chat")


def _build_mode_strip(main: MainWindow) -> QWidget:
    """Chat-first mode bar: Agent center + jumps to Market / Learn."""
    strip = QWidget()
    row = QHBoxLayout(strip)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    modes = QLabel("Режимы")
    modes.setStyleSheet("color: #64748b;")
    row.addWidget(modes)

    main.chat_mode_agent_btn = QPushButton("Агент")
    main.chat_mode_agent_btn.setToolTip("Диалог с агентом (архитектура, план, apply)")
    main.chat_mode_agent_btn.setMaximumWidth(88)
    main.chat_mode_market_btn = QPushButton("Market")
    main.chat_mode_market_btn.setToolTip("Live paper Binance — режим Chat→Market")
    main.chat_mode_market_btn.setMaximumWidth(88)
    main.chat_mode_learn_btn = QPushButton("Обучение")
    main.chat_mode_learn_btn.setToolTip("Models → ML: PyTorch и прогресс Market learning")
    main.chat_mode_learn_btn.setMaximumWidth(96)
    row.addWidget(main.chat_mode_agent_btn)
    row.addWidget(main.chat_mode_market_btn)
    row.addWidget(main.chat_mode_learn_btn)

    main.chat_llm_source_label = QLabel("LLM: —")
    main.chat_llm_source_label.setStyleSheet("color: #64748b; font-size: 11px;")
    main.chat_llm_source_label.setToolTip("Активный источник ответа (Models → Источник)")
    row.addWidget(main.chat_llm_source_label)

    main.chat_mode_status_label = QLabel("Market: —")
    main.chat_mode_status_label.setWordWrap(True)
    main.chat_mode_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    main.chat_mode_status_label.setStyleSheet("color: #64748b;")
    row.addWidget(main.chat_mode_status_label, 1)
    return strip


def _build_dialog_page(main: MainWindow) -> QWidget:
    """Agent chat: transcript + compose left, context panel right. No market here."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 6, 0, 0)
    layout.setSpacing(6)

    layout.addWidget(_build_mode_strip(main))

    main.chat_transcript = QTextBrowser()
    main.chat_transcript.setReadOnly(True)
    main.chat_transcript.setOpenExternalLinks(False)
    main.chat_transcript.setOpenLinks(False)
    main.chat_transcript.setPlaceholderText("Dialog with Eurika…")
    main.chat_transcript.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    main.chat_transcript.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    main.chat_transcript.document().setDocumentMargin(8)
    main.chat_transcript.setStyleSheet("QTextBrowser { border: none; padding: 4px; }")
    main._chat_block_payloads = {}

    compose = QWidget()
    compose_layout = QVBoxLayout(compose)
    compose_layout.setContentsMargins(0, 0, 0, 0)
    compose_layout.setSpacing(4)

    main.chat_input = ChatInputEdit()
    main.chat_input.setPlaceholderText(
        "Спроси агента… Ctrl+V — скриншот · @модуль · Ctrl+Enter · ↑/↓"
    )
    main.chat_input.setMinimumHeight(48)
    main.chat_input.setMaximumHeight(140)
    compose_layout.addWidget(main.chat_input)

    main.chat_pending_label = QLabel("Pending plan: none")
    main.chat_pending_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    compose_layout.addWidget(main.chat_pending_label)

    main.chat_typing_label = QLabel("")
    main.chat_typing_label.setStyleSheet("color: #64748b; font-style: italic;")
    main.chat_typing_label.setVisible(False)
    compose_layout.addWidget(main.chat_typing_label)

    primary = QHBoxLayout()
    main.chat_send_btn = QPushButton("Send")
    main.chat_cancel_btn = QPushButton("Cancel")
    main.chat_cancel_btn.setEnabled(False)
    main.chat_cancel_btn.setToolTip("Прервать текущий запрос к LLM")
    main.chat_clear_btn = QPushButton("Clear")
    main.chat_clear_btn.setToolTip("Очистить диалог")
    primary.addWidget(main.chat_send_btn)
    primary.addWidget(main.chat_cancel_btn)
    primary.addWidget(main.chat_clear_btn)
    primary.addStretch(1)
    compose_layout.addLayout(primary)

    secondary = QHBoxLayout()
    main.chat_apply_btn = QPushButton("Apply")
    main.chat_reject_btn = QPushButton("Reject")
    main.chat_diff_btn = QPushButton("Diff")
    main.chat_apply_btn.setEnabled(False)
    main.chat_reject_btn.setEnabled(False)
    main.chat_diff_btn.setEnabled(False)
    main.chat_diff_btn.setToolTip("Обновить unified diff pending-плана")
    main.chat_feedback_helpful_btn = QPushButton("Полезно")
    main.chat_feedback_not_btn = QPushButton("Не то")
    main.chat_feedback_helpful_btn.setEnabled(False)
    main.chat_feedback_not_btn.setEnabled(False)
    main.chat_feedback_helpful_btn.setToolTip("Ответ был полезен")
    main.chat_feedback_not_btn.setToolTip("Ответ не подошёл")
    secondary.addWidget(main.chat_apply_btn)
    secondary.addWidget(main.chat_reject_btn)
    secondary.addWidget(main.chat_diff_btn)
    secondary.addWidget(main.chat_feedback_helpful_btn)
    secondary.addWidget(main.chat_feedback_not_btn)
    secondary.addStretch(1)
    compose_layout.addLayout(secondary)

    chat_split = QSplitter(Qt.Orientation.Vertical)
    chat_split.addWidget(main.chat_transcript)
    chat_split.addWidget(compose)
    chat_split.setChildrenCollapsible(False)
    chat_split.setStretchFactor(0, 4)
    chat_split.setStretchFactor(1, 1)

    context = QWidget()
    context_layout = QVBoxLayout(context)
    context_layout.setContentsMargins(0, 0, 0, 0)
    context_layout.setSpacing(6)
    context_title = QLabel("Контекст")
    context_title.setStyleSheet("font-weight: 600;")
    context_layout.addWidget(context_title)

    main.chat_goal_view = QTextEdit()
    main.chat_goal_view.setReadOnly(True)
    main.chat_goal_view.setPlaceholderText(
        "Цель / pending Diff / итог — после scan, Apply или «что получилось?»"
    )
    context_layout.addWidget(main.chat_goal_view, 1)

    main.chat_diff_view = QTextEdit()
    main.chat_diff_view.setReadOnly(True)
    main.chat_diff_view.setPlaceholderText(
        "Diff pending-плана (авто; Apply после просмотра)"
    )
    main.chat_diff_view.setStyleSheet("font-family: monospace; font-size: 12px;")
    main.chat_diff_view.setMinimumHeight(64)
    context_layout.addWidget(main.chat_diff_view, 1)

    jump_row = QHBoxLayout()
    jump_row.setSpacing(6)
    main.chat_focus_terminal_btn = QPushButton("Terminal")
    main.chat_focus_terminal_btn.setToolTip("Открыть вкладку Terminal")
    main.chat_focus_terminal_btn.setMaximumWidth(96)
    main.chat_focus_approvals_btn = QPushButton("Approvals")
    main.chat_focus_approvals_btn.setToolTip("Открыть вкладку Approvals (team-mode plan / diff)")
    main.chat_focus_approvals_btn.setMaximumWidth(96)
    jump_row.addWidget(main.chat_focus_terminal_btn)
    jump_row.addWidget(main.chat_focus_approvals_btn)
    jump_row.addStretch(1)
    context_layout.addLayout(jump_row)

    main_split = QSplitter(Qt.Orientation.Horizontal)
    main_split.addWidget(chat_split)
    main_split.addWidget(context)
    main_split.setChildrenCollapsible(False)
    main_split.setStretchFactor(0, 3)
    main_split.setStretchFactor(1, 1)
    main_split.setSizes([720, 300])
    layout.addWidget(main_split, 1)
    return page


def _fixed_field(widget: QWidget, width: int = SPIN_MAX_WIDTH) -> QWidget:
    widget.setMaximumWidth(width)
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addWidget(widget)
    row.addStretch(1)
    return wrap


def _market_hbox(*widgets: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for widget in widgets:
        row.addWidget(widget)
    row.addStretch(1)
    return row


def _build_ticker_column(
    *,
    title: str,
    list_widget: QListWidget,
    edit: QLineEdit,
    add_btn: QPushButton,
    del_btn: QPushButton,
    extra_btn: QPushButton | None = None,
) -> QWidget:
    col = QVBoxLayout()
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(4)
    col.addWidget(QLabel(title))
    col.addWidget(list_widget, 1)
    edit_row = QHBoxLayout()
    edit_row.setSpacing(4)
    edit_row.addWidget(edit, 1)
    edit_row.addWidget(add_btn)
    edit_row.addWidget(del_btn)
    if extra_btn is not None:
        edit_row.addWidget(extra_btn)
    col.addLayout(edit_row)
    wrap = QWidget()
    wrap.setLayout(col)
    return wrap


def _build_market_page(main: MainWindow) -> QWidget:
    """Live paper: always-visible ops bar + event log; settings on the side."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 6, 0, 0)
    layout.setSpacing(6)

    main.market_live_check = QCheckBox("Live paper")
    main.market_live_check.setToolTip("Тики по свечам Binance; ордера на биржу не уходят")
    main.market_auto_check = QCheckBox("Авто")
    main.market_auto_check.setToolTip("Периодический тик при включённом Live paper")
    main.market_tick_btn = QPushButton("Тик")
    main.market_tick_btn.setMinimumWidth(72)
    main.market_tick_btn.setToolTip("Один цикл: sync → анализ → бумага → итог")
    main.market_kind_combo = QComboBox()
    main.market_kind_combo.addItems(["Spot", "Futures", "Both"])
    main.market_kind_combo.setCurrentText("Spot")
    main.market_kind_combo.setMaximumWidth(96)
    main.market_kind_combo.setToolTip(
        "Spot / USD-M Futures / оба. Тикеры — в панели справа. Без ордеров."
    )
    main.market_candle_combo = QComboBox()
    main.market_candle_combo.addItems(["15m", "1h"])
    main.market_candle_combo.setCurrentText("15m")
    main.market_candle_combo.setMaximumWidth(64)
    main.market_candle_combo.setToolTip("Таймфрейм свечей (15m быстрее даёт итоги)")
    main.market_horizon_spin = QSpinBox()
    main.market_horizon_spin.setRange(1, 24)
    main.market_horizon_spin.setValue(2)
    main.market_horizon_spin.setPrefix("гор. ")
    main.market_horizon_spin.setMaximumWidth(88)
    main.market_horizon_spin.setToolTip(
        "Макс. удержание в барах основного ТФ (если TP/SL не сработали раньше на 1m)"
    )
    main.market_exec_1m_check = QCheckBox("1m TP/SL")
    main.market_exec_1m_check.setChecked(True)
    main.market_exec_1m_check.setToolTip(
        "Сигнал на 15m/1h, вход/выход на 1m: TP/SL/trail ставит ML (спины — потолок/запасной)"
    )
    main.market_interval_spin = QSpinBox()
    main.market_interval_spin.setRange(15, 3600)
    main.market_interval_spin.setValue(60)
    main.market_interval_spin.setPrefix("каждые ")
    main.market_interval_spin.setSuffix(" с")
    main.market_interval_spin.setMaximumWidth(130)
    main.market_interval_spin.setToolTip("Интервал авто-тика")
    main.market_drop_orphans_btn = QPushButton("Сброс сирот")
    main.market_drop_orphans_btn.setToolTip(
        "Удалить открытые paper вне текущих списков Spot/Futures (без метки, сразу)"
    )
    main.market_report_btn = QPushButton("Отчёт")
    main.market_report_btn.setToolTip(
        "Сводка в ленту: opens/pending, Portfolio агент (holistic), MLP paper, обучение голов, LLM shadow"
    )
    main.market_clear_btn = QPushButton("Очистить")
    main.market_clear_btn.setToolTip("Очистить ленту Market (Dialog не трогает)")

    header = QWidget()
    header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(4)
    header_layout.addLayout(
        _market_hbox(
            main.market_live_check,
            main.market_auto_check,
            main.market_tick_btn,
            main.market_kind_combo,
            main.market_candle_combo,
            main.market_horizon_spin,
            main.market_exec_1m_check,
        )
    )
    header_layout.addLayout(
        _market_hbox(
            main.market_interval_spin,
            main.market_drop_orphans_btn,
            main.market_report_btn,
            main.market_clear_btn,
        )
    )

    main.market_bank_label = QLabel("equity=— · маржа — · Δ=—")
    main.market_bank_label.setWordWrap(True)
    main.market_bank_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    main.market_bank_label.setStyleSheet("font-weight: 600;")
    main.market_bank_label.setToolTip(
        "Бумажный банк (старт 1000 USDT): equity, занятая маржа, Δ от старта, PnL$ live"
    )
    header_layout.addWidget(main.market_bank_label)

    main.market_status_label = QLabel("выкл · BTCUSDT 1h · без ордеров на биржу")
    main.market_status_label.setWordWrap(True)
    main.market_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    main.market_status_label.setStyleSheet(get_secondary_hint())
    header_layout.addWidget(main.market_status_label)
    layout.addWidget(header)

    main.market_transcript = QTextEdit()
    main.market_transcript.setReadOnly(True)
    main.market_transcript.setAcceptRichText(True)
    main.market_transcript.setPlaceholderText(
        "Лента: сделки · итоги · обучение · LLM · ошибки (без sync/analysis/hold на каждый тик)"
    )
    main.market_transcript.setMinimumHeight(80)

    main.market_micro_train_check = QCheckBox("Дообучение")
    main.market_micro_train_check.setChecked(True)
    main.market_micro_train_check.setToolTip("После итога — короткий train на CPU")
    main.market_llm_learn_check = QCheckBox("LLM обучение")
    main.market_llm_learn_check.setChecked(False)
    main.market_llm_learn_check.setToolTip(
        "Каждые 15 мин Cursor читает TF1 и TF2 (ниже) и учит MLP. "
        "Не ордер и не замена argmax"
    )
    main.market_portfolio_check = QCheckBox("Portfolio агент")
    main.market_portfolio_check.setChecked(False)
    main.market_portfolio_check.setToolTip(
        "Каждые 15 мин holistic агент: spot/fut/earn paper, единый cash pool, "
        "метки в teacher. Не live-ордера и не MLP exam"
    )
    main.market_portfolio_once_btn = QPushButton("Цикл")
    main.market_portfolio_once_btn.setToolTip("Один portfolio-цикл сейчас (нужен CURSOR_API_KEY)")
    main.market_llm_tf1_combo = QComboBox()
    main.market_llm_tf1_combo.addItems(["5m", "15m", "1h", "4h"])
    main.market_llm_tf1_combo.setCurrentText("15m")
    main.market_llm_tf1_combo.setToolTip("Первый ТФ для LLM-разбора (обязательно оба)")
    main.market_llm_tf2_combo = QComboBox()
    main.market_llm_tf2_combo.addItems(["5m", "15m", "1h", "4h"])
    main.market_llm_tf2_combo.setCurrentText("1h")
    main.market_llm_tf2_combo.setToolTip("Второй ТФ для LLM-разбора (обязательно оба)")
    main.market_explore_check = QCheckBox("Исследование")
    main.market_explore_check.setChecked(False)
    main.market_explore_check.setToolTip(
        "Если модель говорит ДЕРЖАТЬ — теневой BUY/SELL для меток (без риска для бумажного банка)"
    )
    main.market_explore_cap_spin = QSpinBox()
    main.market_explore_cap_spin.setRange(0, 5000)
    main.market_explore_cap_spin.setValue(80)
    main.market_explore_cap_spin.setToolTip(
        "Лимит меток исследования в сессии (live + explore-тени). 0 = без лимита"
    )
    main.market_explore_cap_spin.setPrefix("до ")
    main.market_explore_cap_spin.setSuffix(" live")
    main.market_explore_reset_btn = QPushButton("Сброс счётчика")
    main.market_explore_reset_btn.setToolTip(
        "Обнулить счётчик исследования (live к cap). История paper и веса ML не удаляются."
    )
    main.market_explore_cap_spin.setEnabled(False)
    main.market_explore_reset_btn.setEnabled(False)

    learn_box = QGroupBox("Обучение")
    learn_form = QFormLayout(learn_box)
    learn_form.setContentsMargins(8, 8, 8, 8)
    learn_form.setSpacing(4)
    learn_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    learn_form.addRow(main.market_micro_train_check)
    learn_form.addRow(main.market_llm_learn_check)
    learn_form.addRow(main.market_portfolio_check)
    learn_form.addRow("", main.market_portfolio_once_btn)
    learn_form.addRow("TF1", _fixed_field(main.market_llm_tf1_combo, 72))
    learn_form.addRow("TF2", _fixed_field(main.market_llm_tf2_combo, 72))
    learn_form.addRow(main.market_explore_check)
    learn_form.addRow("Лимит", _fixed_field(main.market_explore_cap_spin, 110))
    learn_form.addRow("", main.market_explore_reset_btn)

    main.market_tp_spin = QDoubleSpinBox()
    main.market_tp_spin.setRange(0.0, 10.0)
    main.market_tp_spin.setSingleStep(0.1)
    main.market_tp_spin.setValue(1.0)
    main.market_tp_spin.setSuffix(" %")
    main.market_tp_spin.setToolTip(
        "Потолок TP % (ML ставит сама; 0 = без потолка, только модель/эвристика)"
    )
    main.market_sl_spin = QDoubleSpinBox()
    main.market_sl_spin.setRange(0.0, 10.0)
    main.market_sl_spin.setSingleStep(0.1)
    main.market_sl_spin.setValue(1.0)
    main.market_sl_spin.setSuffix(" %")
    main.market_sl_spin.setToolTip("Потолок SL % (ML ставит сама; 0 = без потолка)")
    main.market_trail_spin = QDoubleSpinBox()
    main.market_trail_spin.setRange(0.0, 10.0)
    main.market_trail_spin.setSingleStep(0.1)
    main.market_trail_spin.setValue(0.8)
    main.market_trail_spin.setSuffix(" %")
    main.market_trail_spin.setToolTip("Потолок trailing % (ML ставит сама; 0 = без потолка)")

    levels_box = QGroupBox("Потолки TP/SL")
    levels_form = QFormLayout(levels_box)
    levels_form.setContentsMargins(8, 8, 8, 8)
    levels_form.setSpacing(4)
    levels_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    levels_form.addRow("TP", _fixed_field(main.market_tp_spin))
    levels_form.addRow("SL", _fixed_field(main.market_sl_spin))
    levels_form.addRow("trail", _fixed_field(main.market_trail_spin))

    main.market_spot_list = QListWidget()
    main.market_spot_list.setMinimumHeight(72)
    main.market_spot_list.setToolTip("Spot-тикеры для обучения (добавляйте вручную)")
    main.market_spot_edit = QLineEdit()
    main.market_spot_edit.setPlaceholderText("BTCUSDT")
    main.market_spot_add_btn = QPushButton("+")
    main.market_spot_add_btn.setFixedWidth(28)
    main.market_spot_add_btn.setToolTip("Добавить spot-тикер")
    main.market_spot_del_btn = QPushButton("−")
    main.market_spot_del_btn.setFixedWidth(28)
    main.market_spot_del_btn.setToolTip("Удалить выбранный spot-тикер")
    main.market_spot_fill_btn = QPushButton("Заполнить")
    main.market_spot_fill_btn.setToolTip(
        "Один раз подставить пары из spot-балансов (до 8). Дальше правите вручную."
    )
    main.market_futures_list = QListWidget()
    main.market_futures_list.setMinimumHeight(72)
    main.market_futures_list.setToolTip("USD-M Futures тикеры (отдельно от spot)")
    main.market_futures_edit = QLineEdit()
    main.market_futures_edit.setPlaceholderText("BTCUSDT")
    main.market_futures_add_btn = QPushButton("+")
    main.market_futures_add_btn.setFixedWidth(28)
    main.market_futures_add_btn.setToolTip("Добавить futures-тикер (проверка fapi)")
    main.market_futures_del_btn = QPushButton("−")
    main.market_futures_del_btn.setFixedWidth(28)
    main.market_futures_del_btn.setToolTip("Удалить выбранный futures-тикер")

    tickers_box = QGroupBox("Тикеры")
    tickers_row = QHBoxLayout(tickers_box)
    tickers_row.setContentsMargins(8, 8, 8, 8)
    tickers_row.setSpacing(8)
    tickers_row.addWidget(
        _build_ticker_column(
            title="Spot",
            list_widget=main.market_spot_list,
            edit=main.market_spot_edit,
            add_btn=main.market_spot_add_btn,
            del_btn=main.market_spot_del_btn,
            extra_btn=main.market_spot_fill_btn,
        ),
        1,
    )
    tickers_row.addWidget(
        _build_ticker_column(
            title="Futures",
            list_widget=main.market_futures_list,
            edit=main.market_futures_edit,
            add_btn=main.market_futures_add_btn,
            del_btn=main.market_futures_del_btn,
        ),
        1,
    )

    settings = QWidget()
    settings_layout = QVBoxLayout(settings)
    settings_layout.setContentsMargins(0, 0, 0, 0)
    settings_layout.setSpacing(8)
    settings_layout.addWidget(tickers_box, 1)
    settings_layout.addWidget(learn_box)
    settings_layout.addWidget(levels_box)
    settings_scroll = VerticalScrollArea(settings, hint_width=320, hint_height=180)

    split = QSplitter(Qt.Orientation.Horizontal)
    split.addWidget(main.market_transcript)
    split.addWidget(settings_scroll)
    split.setChildrenCollapsible(False)
    split.setCollapsible(1, True)
    split.setStretchFactor(0, 3)
    split.setStretchFactor(1, 1)
    split.setSizes([720, 320])
    layout.addWidget(split, 1)

    main._market_timer = None
    main._market_tick_busy = False
    main._market_tick_worker = None
    main._market_llm_timer = None
    main._market_llm_worker = None
    main._market_llm_warned_no_key = False
    return page

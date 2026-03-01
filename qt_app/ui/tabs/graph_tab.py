"""Graph tab: dependency graph via QWebEngineView or fallback. ROADMAP 3.1-arch.3."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget

from ..main_window_helpers import create_graph_page

if TYPE_CHECKING:
    from ..main_window import MainWindow


def build_graph_tab(main: MainWindow) -> None:
    """Build Graph tab: lazy-load QWebEngineView on first use."""
    tab = QWidget()
    layout = QVBoxLayout(tab)
    row = QHBoxLayout()
    main.refresh_graph_btn = QPushButton("Refresh graph")
    main.refresh_graph_btn.setToolTip("Load dependency graph from self_map.json (run scan first)")
    row.addWidget(main.refresh_graph_btn)
    main.graph_hint = QLabel("Run eurika scan . to generate self_map.json")
    main.graph_hint.setStyleSheet("color: gray; font-size: 11px;")
    row.addWidget(main.graph_hint, 1)
    layout.addLayout(row)
    main.graph_placeholder = QWidget()
    main.graph_placeholder_layout = QVBoxLayout(main.graph_placeholder)
    main.graph_placeholder_layout.setContentsMargins(0, 0, 0, 0)
    main._graph_web_view = None
    main._graph_table_fallback = None
    main._graph_webengine_available = None
    layout.addWidget(main.graph_placeholder, 1)
    main.graph_tab_index = main.tabs.addTab(tab, "Graph")


def on_graph_node_explain(main: MainWindow, module: str) -> None:
    """Handle double-click on graph node: show Explain for module."""
    text, err = main._api.explain_module(module, window=main.window_spin.value())
    if err:
        QMessageBox.warning(main, f"Explain: {module}", err)
        return
    msg = (text or "").strip()
    if not msg:
        msg = "No explanation available."
    QMessageBox.information(main, f"Explain: {module}", msg)


def ensure_graph_widget(main: MainWindow) -> None:
    """Lazy-create WebEngine or fallback on first use."""
    if main._graph_webengine_available is not None:
        return
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        view = QWebEngineView()
        page = create_graph_page(view, lambda mod: on_graph_node_explain(main, mod))
        if page is not None:
            view.setPage(page)
        view.setMinimumHeight(300)
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main.graph_placeholder_layout.addWidget(view)
        main._graph_web_view = view
        main._graph_webengine_available = True
    except ImportError:
        main._graph_webengine_available = False
        fallback = QTextEdit()
        fallback.setReadOnly(True)
        fallback.setPlaceholderText("QWebEngineWidgets not available. Install PySide6-Addons.")
        main.graph_placeholder_layout.addWidget(fallback)
        main._graph_table_fallback = fallback


def refresh_graph(main: MainWindow) -> None:
    """Load graph from API and render in WebEngine or fallback."""
    ensure_graph_widget(main)
    data = main._api.get_graph()
    error = data.get("error")
    if error:
        msg = f"{error}\nPath: {data.get('path', '')}"
        if main._graph_web_view is not None:
            _render_graph_html(main, {"nodes": [], "edges": [], "error": msg})
        elif main._graph_table_fallback is not None:
            main._graph_table_fallback.setPlainText(msg)
        if main.graph_hint:
            main.graph_hint.setText("No graph — run eurika scan . first")
        return
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    if main._graph_web_view is not None:
        _render_graph_html(main, {"nodes": nodes, "edges": edges})
    elif main._graph_table_fallback is not None:
        lines = [f"Nodes: {len(nodes)}, Edges: {len(edges)}"]
        for n in nodes[:50]:
            lines.append(f"  {n.get('id', '')} (fan-in: {n.get('fan_in', 0)}, fan-out: {n.get('fan_out', 0)})")
        if len(nodes) > 50:
            lines.append(f"  ... and {len(nodes) - 50} more")
        main._graph_table_fallback.setPlainText("\n".join(lines))
    if main.graph_hint:
        main.graph_hint.setText(f"{len(nodes)} modules, {len(edges)} dependencies")


def _render_graph_html(main: MainWindow, payload: dict[str, Any]) -> None:
    """Render vis-network graph in QWebEngineView via embedded HTML."""
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    err_msg = payload.get("error", "")
    if err_msg:
        err_esc = err_msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = f'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><pre style="padding:1em;color:#c00">{err_esc}</pre></body></html>'
    else:
        nodes_js = json.dumps(nodes, ensure_ascii=False).replace("</", "<\\/")
        edges_js = json.dumps(edges, ensure_ascii=False).replace("</", "<\\/")
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }}
#net {{ position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; }}
</style></head>
<body><div id="net"></div>
<script>
var nodes = new vis.DataSet({nodes_js});
var edges = new vis.DataSet({edges_js});
var container = document.getElementById('net');
var data = {{ nodes: nodes, edges: edges }};
var options = {{
  nodes: {{ shape: 'dot', size: 12, font: {{ size: 10 }} }},
  edges: {{ arrows: 'to' }},
  physics: {{ barnesHut: {{ gravitationalConstant: -3000, centralGravity: 0.1, springLength: 100 }} }}
}};
var network = new vis.Network(container, data, options);
network.on('doubleClick', function(params) {{
  if (params.nodes && params.nodes[0]) {{
    var mod = params.nodes[0];
    window.location = 'eurika:explain/' + encodeURIComponent(mod);
  }}
}});
</script></body></html>"""
    if main._graph_web_view is not None:
        main._graph_web_view.setHtml(html, "https://unpkg.com/")

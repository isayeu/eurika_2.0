"""
Architecture History v0.6

Stores architectural snapshots over time and derives trends:
- complexity growth
- centralization drift
- smell dynamics
- basic regression detection
- version, git_commit (optional), risk_score
"""
from __future__ import annotations
import json
import re
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional
from eurika.analysis.graph import ProjectGraph
from eurika.analysis.metrics import summarize_graph
from eurika.smells.detector import ArchSmell
from eurika.smells.rules import compute_health

def _ascii_bar(value: int, max_val: int=100, width: int=10) -> str:
    """Simple ASCII bar: [████░░░░░░] 40/100."""
    if max_val <= 0:
        return '[] 0'
    filled = max(0, min(width, int(width * value / max_val)))
    bar = '█' * filled + '░' * (width - filled)
    return f'[{bar}] {value}/{max_val}'

def _read_version(project_root: Path) -> Optional[str]:
    """Read version from pyproject.toml. Returns None if not found."""
    path = project_root / 'pyproject.toml'
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding='utf-8')
        m = re.search('version\\s*=\\s*["\\\']([^"\\\']+)["\\\']', text)
        return m.group(1) if m else None
    except (OSError, UnicodeDecodeError):
        return None

def _get_git_commit(project_root: Path) -> Optional[str]:
    """Get current git commit hash. Returns None if not a git repo or git unavailable."""
    if not (project_root / '.git').exists():
        return None
    try:
        r = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=project_root, capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout:
            return r.stdout.strip()[:12]
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None

@dataclass
class HistoryPoint:
    timestamp: float
    modules: int
    dependencies: int
    cycles: int
    max_degree: int
    total_smells: int
    smell_counts: Dict[str, int]
    version: Optional[str] = None
    git_commit: Optional[str] = None
    risk_score: Optional[int] = None

class ArchitectureHistory:
    """
    Append-only history of architecture snapshots.
    v0.1: simple JSON file in project root, trend over last N points.
    """

    def __init__(self, storage_path: Optional[Path]=None):
        self.storage_path = storage_path or Path('architecture_history.json')
        self._points: List[HistoryPoint] = []
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding='utf-8'))
            for item in raw.get('history', []):
                self._points.append(HistoryPoint(timestamp=item.get('timestamp', time.time()), modules=item.get('modules', 0), dependencies=item.get('dependencies', 0), cycles=item.get('cycles', 0), max_degree=item.get('max_degree', 0), total_smells=item.get('total_smells', 0), smell_counts=item.get('smell_counts', {}), version=item.get('version'), git_commit=item.get('git_commit'), risk_score=item.get('risk_score')))
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        data = {'history': [asdict(p) for p in self._points]}
        try:
            self.storage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        except OSError:
            pass

    def _smell_counts(self, smells: List[ArchSmell]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for s in smells:
            counts[s.type] = counts.get(s.type, 0) + 1
        return counts

    def append(self, graph: ProjectGraph, smells: List[ArchSmell], summary: Dict) -> None:
        """Append new snapshot to history."""
        project_root = self.storage_path.parent.resolve()
        g_sum = summarize_graph(graph)
        fan = graph.fan_in_out()
        degrees = {n: fi + fo for n, (fi, fo) in fan.items()}
        max_degree = max(degrees.values()) if degrees else 0
        smell_counts = self._smell_counts(smells)
        total_smells = sum(smell_counts.values())
        sys = summary.get('system', {})
        version = _read_version(project_root)
        git_commit = _get_git_commit(project_root)
        trends = self.trend(window=5)
        health = compute_health(summary, smells, trends)
        risk_score = int(health['score'])
        point = HistoryPoint(timestamp=time.time(), modules=int(sys.get('modules', g_sum.get('nodes', 0))), dependencies=int(sys.get('dependencies', g_sum.get('edges', 0))), cycles=int(sys.get('cycles', len(g_sum.get('cycles', [])))), max_degree=int(max_degree), total_smells=int(total_smells), smell_counts=smell_counts, version=version, git_commit=git_commit, risk_score=risk_score)
        self._points.append(point)
        self._save()

    def _window(self, window: int) -> List[HistoryPoint]:
        if window <= 0 or window > len(self._points):
            return list(self._points)
        return self._points[-window:]

    def trend(self, window: int=5) -> Dict[str, str]:
        """
        Compute simple trends over last N points:
        - increasing / decreasing / stable for complexity, smells, centralization.
        """
        pts = self._window(window)
        if len(pts) < 2:
            return {'complexity': 'insufficient_data', 'smells': 'insufficient_data', 'centralization': 'insufficient_data'}

        def _dir(values: List[int]) -> str:
            if len(values) < 2:
                return 'stable'
            if values[-1] > values[0]:
                return 'increasing'
            if values[-1] < values[0]:
                return 'decreasing'
            return 'stable'
        complexity_series = [p.modules + p.dependencies for p in pts]
        smells_series = [p.total_smells for p in pts]
        central_series = [p.max_degree for p in pts]
        return {'complexity': _dir(complexity_series), 'smells': _dir(smells_series), 'centralization': _dir(central_series)}

    def detect_regressions(self, window: int=5) -> List[str]:
        """
        Heuristic regression detection:
        - new cycles appear
        - smells jump up (total and per-type: god_module, bottleneck, hub)
        - centralization grows fast
        """
        pts = self._window(window)
        notes: List[str] = []
        if len(pts) < 2:
            return notes
        oldest, newest = (pts[0], pts[-1])
        old_counts = oldest.smell_counts
        new_counts = newest.smell_counts
        if newest.cycles > oldest.cycles:
            notes.append(f'Cycles increased: {oldest.cycles} → {newest.cycles}')
        if newest.total_smells > oldest.total_smells:
            notes.append(f'Total smells increased: {oldest.total_smells} → {newest.total_smells}')
        for smell_type in ('god_module', 'bottleneck', 'hub'):
            old_n = old_counts.get(smell_type, 0)
            new_n = new_counts.get(smell_type, 0)
            if new_n > old_n:
                notes.append(f'{smell_type} increased: {old_n} → {new_n}')
        if newest.max_degree > oldest.max_degree * 1.5 and oldest.max_degree >= 2:
            notes.append(f'Centralization increased significantly (max degree {oldest.max_degree} → {newest.max_degree})')
        return notes

    def _compute_maturity(self, trends: Dict[str, str], newest: HistoryPoint) -> str:
        """Dynamic maturity based on trends + cycles."""
        if trends['complexity'] == 'insufficient_data':
            return 'insufficient_data'
        no_cycles = newest.cycles == 0
        smells_trend = trends['smells']
        central_trend = trends['centralization']
        if no_cycles and smells_trend == 'decreasing' and (central_trend in {'stable', 'decreasing'}):
            return 'high'
        if no_cycles and smells_trend == 'stable' and (central_trend != 'increasing'):
            return 'medium'
        if not no_cycles or smells_trend == 'increasing':
            return 'low'
        return 'medium-low'

    def _append_trend_section(self, lines: List[str], trends: Dict[str, str]) -> None:
        lines.append('Trend:')
        lines.append(f"- System complexity: {trends['complexity']}")
        lines.append(f"- Centralization: {trends['centralization']}")
        lines.append(f"- Smell count: {trends['smells']}")
        lines.append('')

    def _append_regressions_section(self, lines: List[str], regressions: List[str]) -> None:
        if regressions:
            lines.append('Potential regressions:')
            for r in regressions:
                lines.append(f'- {r}')
        else:
            lines.append('Potential regressions:')
            lines.append('- none detected over the observed window')

    def _append_maturity_section(self, lines: List[str], maturity: str) -> None:
        lines.append('')
        lines.append(f'Maturity (dynamic): {maturity}')
        if maturity == 'high':
            lines.append('Interpretation: architecture is growing or stabilizing with decreasing structural issues. Focus can shift from firefighting to guided evolution.')
        elif maturity == 'medium':
            lines.append('Interpretation: architecture is stable but still centralized. Monitor hubs and bottlenecks to avoid future rigidity.')
        elif maturity == 'low':
            lines.append('Interpretation: structural issues are accumulating. Prioritize breaking emerging bottlenecks and reducing smell growth.')

    def evolution_report(self, window: int=5, ascii_chart: bool=True) -> str:
        pts = self._window(window)
        if not pts:
            return 'No architecture history yet.'
        trends = self.trend(window)
        regressions = self.detect_regressions(window)
        newest = pts[-1]
        oldest = pts[0]
        lines: List[str] = []
        lines.append('ARCHITECTURE EVOLUTION ANALYSIS')
        lines.append('')
        if newest.version is not None:
            lines.append(f'Version: {newest.version}')
        if newest.git_commit is not None:
            lines.append(f'Git: {newest.git_commit}')
        if newest.risk_score is not None:
            if ascii_chart:
                lines.append(f'Risk score: {_ascii_bar(newest.risk_score)}')
            else:
                lines.append(f'Risk score: {newest.risk_score}/100')
        if newest.version is not None or newest.git_commit is not None or newest.risk_score is not None:
            lines.append('')
        if len(pts) >= 2:
            lines.append('Diff metrics (window):')
            lines.append(f'- Modules: {oldest.modules} → {newest.modules} (Δ {newest.modules - oldest.modules})')
            lines.append(f'- Dependencies: {oldest.dependencies} → {newest.dependencies} (Δ {newest.dependencies - oldest.dependencies})')
            lines.append(f'- Cycles: {oldest.cycles} → {newest.cycles} (Δ {newest.cycles - oldest.cycles})')
            lines.append(f'- Total smells: {oldest.total_smells} → {newest.total_smells} (Δ {newest.total_smells - oldest.total_smells})')
            lines.append(f'- Max degree: {oldest.max_degree} → {newest.max_degree} (Δ {newest.max_degree - oldest.max_degree})')
            if oldest.risk_score is not None and newest.risk_score is not None:
                lines.append(f'- Risk score: {oldest.risk_score} → {newest.risk_score} (Δ {newest.risk_score - oldest.risk_score})')
            lines.append('')
            lines.append('Smell history (window):')
            all_types = sorted(set(oldest.smell_counts.keys()) | set(newest.smell_counts.keys()))
            if not all_types:
                lines.append('- no smells recorded in history window')
            else:
                for t in all_types:
                    o = oldest.smell_counts.get(t, 0)
                    n = newest.smell_counts.get(t, 0)
                    delta = n - o
                    lines.append(f'- {t}: {o} → {n} (Δ {delta})')
            lines.append('')
        self._append_trend_section(lines, trends)
        self._append_regressions_section(lines, regressions)
        maturity = self._compute_maturity(trends, newest)
        self._append_maturity_section(lines, maturity)
        return '\n'.join(lines)
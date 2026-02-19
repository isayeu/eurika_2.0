"""
Code Awareness v0.1

Read-only code analysis. No modifications. No patches.
SPEC: scan project, AST analysis, find smells, self_map.json.
"""
import ast
import json
from pathlib import Path
from code_awareness_extracted import FileInfo, Smell
from code_awareness_codeawarenessextracted import CodeAwarenessExtracted
from typing import Any, Dict, List, Optional
MAX_FUNCTION_LINES = 50
MAX_NESTING_DEPTH = 4
MIN_DUPLICATE_LINES = 5

class CodeAwareness:
    """
    Read-only file system and AST analysis.
    Domain: own project only (Eurika).
    """

    def __init__(self, root: Optional[Path]=None):
        self.root = root or Path(__file__).resolve().parent

    def scan_python_files(self) -> List[Path]:
        """
        List all .py files in project, excluding __pycache__ and shelved agent runtime stack.

        Shelved modules (v0.1 observe-only, not part of active architecture):
        - agent_runtime.py
        - selector.py
        - reasoner_dummy.py
        - executor_sandbox.py
        """
        shelved = {'agent_runtime.py', 'selector.py', 'reasoner_dummy.py', 'executor_sandbox.py'}
        skip_dirs = {'venv', '.venv', 'node_modules', '.git'}
        files: List[Path] = []
        for p in self.root.rglob('*.py'):
            if '__pycache__' in str(p):
                continue
            if '.eurika_backups' in p.parts:
                continue
            if any((skip in p.parts for skip in skip_dirs)):
                continue
            if p.name in shelved:
                continue
            files.append(p)
        return sorted(files)

    def extract_imports(self, path: Path) -> List[Dict[str, Any]]:
        """Extract imports from Python file."""
        imports = []
        try:
            content = self.read_file(path)
            tree = ast.parse(content)
            imports.extend(self._extract_import_nodes(tree))
        except (SyntaxError, OSError):
            pass
        return imports

    def _extract_import_nodes(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Walk AST and collect import / from-import nodes into a flat list."""
        imports: List[Dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(self._import_to_dicts(node))
            elif isinstance(node, ast.ImportFrom):
                imports.extend(self._importfrom_to_dicts(node))
        return imports

    def analyze_file(self, path: Path) -> Optional[FileInfo]:
        """Parse Python file, extract structure."""
        try:
            content = self.read_file(path)
            tree = ast.parse(content)
            rel = path.relative_to(self.root) if path.is_relative_to(self.root) else path
            functions = []
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    name = node.name
                    if not name.startswith('_'):
                        functions.append(name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
            return FileInfo(path=str(rel), lines=len(content.splitlines()), functions=functions, classes=classes)
        except (SyntaxError, OSError):
            return None

    def scan_project(self) -> List[FileInfo]:
        """Full project scan. Returns list of FileInfo."""
        infos = []
        for p in self.scan_python_files():
            info = self.analyze_file(p)
            if info:
                infos.append(info)
        return infos

    def _nesting_depth(self, node: ast.AST) -> int:
        """Max nesting depth of node (if/for/while/try/with)."""
        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            child_depths = [self._nesting_depth(n) for n in ast.iter_child_nodes(node)]
            return 1 + max(child_depths) if child_depths else 1
        return max((self._nesting_depth(n) for n in ast.iter_child_nodes(node)), default=0)

    def find_smells(self, path: Path) -> List[Smell]:
        """Find code smells: long functions, deep nesting."""
        smells = []
        try:
            content = self.read_file(path)
            tree = ast.parse(content)
            lines = content.splitlines()
            rel = path.relative_to(self.root) if path.is_relative_to(self.root) else path
            file_str = str(rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    loc = node.name
                    nlines = self._function_lines(node, lines)
                    if nlines > MAX_FUNCTION_LINES:
                        smells.append(Smell(file=file_str, location=loc, kind='long_function', message=f'Function has {nlines} lines (>{MAX_FUNCTION_LINES})', metric=nlines))
                    depth = self._nesting_depth(node)
                    if depth > MAX_NESTING_DEPTH:
                        smells.append(Smell(file=file_str, location=loc, kind='deep_nesting', message=f'Nesting depth {depth} (>{MAX_NESTING_DEPTH})', metric=depth))
        except (SyntaxError, OSError):
            pass
        return smells

    def find_duplicates(self) -> List[Dict[str, Any]]:
        """Find functions with identical normalized bodies (copy-paste)."""
        body_to_locations: Dict[str, List[Dict[str, str]]] = {}
        for p in self.scan_python_files():
            self._collect_file_duplicates(p, body_to_locations)
        duplicates = []
        for body, locs in body_to_locations.items():
            if len(locs) >= 2:
                duplicates.append({'locations': locs, 'count': len(locs)})
        return duplicates

    def _collect_file_duplicates(self, path: Path, body_to_locations: Dict[str, List[Dict[str, str]]]) -> None:
        """Update body_to_locations with duplicate candidates from a single file."""
        try:
            content = self.read_file(path)
            tree = ast.parse(content)
            file_str = self._path_to_file_str(path)
            for node in ast.walk(tree):
                candidate = self._function_duplicate_candidate(content, node, file_str)
                if candidate:
                    normalized, loc = candidate
                    body_to_locations.setdefault(normalized, []).append(loc)
        except (SyntaxError, OSError):
            pass

    def _path_to_file_str(self, path: Path) -> str:
        """Convert path to relative file string for duplicate locations."""
        return str(self._relative_path(path)).replace('\\', '/')

    def _relative_path(self, path: Path) -> Path:
        """Return path relative to project root when possible."""
        return path.relative_to(self.root) if path.is_relative_to(self.root) else path

    def _collect_internal_dependencies(self, imports: List[Dict[str, Any]]) -> List[str]:
        """Keep only imports that resolve to project-internal modules."""
        internal: List[str] = []
        for imp in imports:
            mod = imp.get('module', '')
            if not mod or mod.startswith('_'):
                continue
            stem = mod.split('.')[0]
            if (self.root / f'{stem}.py').exists() or (self.root / stem / '__init__.py').exists():
                internal.append(mod)
        return list(dict.fromkeys(internal))

    @staticmethod
    def _file_info_dict(info: FileInfo) -> Dict[str, Any]:
        """Convert FileInfo to JSON-serializable dict."""
        return {
            'path': info.path,
            'lines': info.lines,
            'functions': info.functions,
            'classes': info.classes,
        }

    def _function_duplicate_candidate(self, content: str, node: ast.AST, file_str: str) -> Optional[tuple[str, Dict[str, Any]]]:
        """Extract normalized body and location if function qualifies as duplicate candidate. Returns None to skip."""
        if not isinstance(node, ast.FunctionDef):
            return None
        if not (node.lineno and node.end_lineno):
            return None
        nlines = node.end_lineno - node.lineno + 1
        if nlines < MIN_DUPLICATE_LINES:
            return None
        segment = ast.get_source_segment(content, node) or ''
        normalized = self._normalize_body(segment)
        if len(normalized) < 50:
            return None
        loc = {'file': file_str, 'function': node.name, 'lines': int(nlines)}
        return (normalized, loc)

    def build_self_map(self) -> dict:
        """Build formalized self-map: modules, files, dependencies."""
        modules = []
        dependencies: Dict[str, List[str]] = {}
        for p in self.scan_python_files():
            rel_str = str(self._relative_path(p)).replace('\\', '/')
            info = self.analyze_file(p)
            imports = self.extract_imports(p)
            if info:
                modules.append(self._file_info_dict(info))
            internal = self._collect_internal_dependencies(imports)
            if internal:
                dependencies[rel_str] = internal
        return {'modules': modules, 'dependencies': dependencies, 'summary': {'files': len(modules), 'total_lines': sum((m['lines'] for m in modules))}}

    def write_self_map(self, output_path: Optional[Path]=None) -> Path:
        """Write self_map.json to project root."""
        path = (output_path or self.root) / 'self_map.json'
        data = self.build_self_map()
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        return path

    def analyze_project(self) -> dict:
        """
        Full analysis: structure + smells + self_map.
        Returns dict suitable for report and memory.
        """
        infos = self.scan_project()
        all_smells: List[Smell] = []
        for p in self.scan_python_files():
            all_smells.extend(self.find_smells(p))
        duplicates = self.find_duplicates()
        self_map = self.build_self_map()
        return {
            'structure': [self._file_info_dict(i) for i in infos],
            'smells': [
                {
                    'file': s.file,
                    'location': s.location,
                    'kind': s.kind,
                    'message': s.message,
                    'metric': s.metric,
                }
                for s in all_smells
            ],
            'self_map': self_map,
            'duplicates': duplicates,
            'summary': {
                'files': len(infos),
                'total_lines': sum((i.lines for i in infos)),
                'smells_count': len(all_smells),
                'duplicates_count': len(duplicates),
            },
        }

    def read_file(self, path: Path):
        return CodeAwarenessExtracted.read_file(path)

    def _import_to_dicts(self, node: ast.Import):
        return CodeAwarenessExtracted._import_to_dicts(node)

    def _importfrom_to_dicts(self, node: ast.ImportFrom):
        return CodeAwarenessExtracted._importfrom_to_dicts(node)

    def _function_lines(self, node: ast.FunctionDef, source_lines: List[str]):
        return CodeAwarenessExtracted._function_lines(node, source_lines)

    def _normalize_body(self, text: str):
        return CodeAwarenessExtracted._normalize_body(text)

# TODO: Refactor code_awareness.py (god_module -> split_module)
# Suggested steps:
# - Extract coherent sub-responsibilities into separate modules (e.g. core, analysis, reporting).
# - Identify distinct concerns and split this module into focused units.
# - Reduce total degree (fan-in + fan-out) via extraction.
# - Extract from imports: code_awareness_extracted.py, code_awareness_codeawarenessextracted.py.
# - Consider grouping callers: tests/test_runtime_scan.py, runtime_scan.py, code_awareness_api.py.

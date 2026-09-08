"""Tests for eurika.refactor.extract_function (extract nested function, extract block to helper)."""
import ast
from pathlib import Path

from eurika.refactor.extract_function import (
    extract_block_to_helper,
    extract_nested_function,
    suggest_extract_block,
    suggest_extract_nested_function,
)

def test_suggest_extract_nested_function_finds_self_contained(tmp_path: Path) -> None:
    """suggest_extract_nested_function returns nested function name when it doesn't use parent locals."""
    code = '\ndef long_foo():\n    """Long function with nested helper."""\n    x = 1\n    y = 2\n\n    def inner_helper(a, b):\n        """Helper that only uses its args."""\n        return a + b\n\n    return inner_helper(x, y)\n'
    (tmp_path / 'mod.py').write_text(code)
    sugg = suggest_extract_nested_function(tmp_path / 'mod.py', 'long_foo')
    assert sugg is not None
    assert sugg[0] == 'inner_helper'
    assert sugg[1] >= 3
    assert sugg[2] == []  # no extra params

def test_suggest_extract_nested_function_skips_when_uses_parent_locals(tmp_path: Path) -> None:
    """suggest_extract_nested_function returns None when nested uses parent's variables."""
    code = "\ndef long_foo():\n    x = 1\n    def inner():\n        return x  # uses parent's x\n    return inner()\n"
    (tmp_path / 'mod.py').write_text(code)
    sugg = suggest_extract_nested_function(tmp_path / 'mod.py', 'long_foo')
    assert sugg is None

def test_suggest_extract_nested_function_skips_when_nonlocal(tmp_path: Path) -> None:
    """suggest_extract_nested_function returns None when nested has nonlocal (modifies outer scope)."""
    code = '\ndef long_foo():\n    count = 0\n    def bump():\n        nonlocal count\n        count += 1\n    bump()\n    return count\n'
    (tmp_path / 'mod.py').write_text(code)
    sugg = suggest_extract_nested_function(tmp_path / 'mod.py', 'long_foo')
    assert sugg is None

def test_extract_nested_function_moves_to_module_level(tmp_path: Path) -> None:
    """extract_nested_function moves nested function before parent."""
    code = 'def long_foo():\n    def helper():\n        return 42\n    return helper()\n'
    (tmp_path / 'mod.py').write_text(code)
    result = extract_nested_function(tmp_path / 'mod.py', 'long_foo', 'helper')
    assert result is not None
    (tmp_path / 'mod.py').write_text(result)
    content = (tmp_path / 'mod.py').read_text()
    assert 'def helper():' in content
    assert 'def long_foo():' in content
    assert content.index('def helper():') < content.index('def long_foo():')
    assert 'return helper()' in content
    assert content.count('def helper():') == 1

def test_extract_nested_function_returns_none_when_not_found(tmp_path: Path) -> None:
    """extract_nested_function returns None when nested doesn't exist."""
    (tmp_path / 'mod.py').write_text('def foo(): pass\n')
    assert extract_nested_function(tmp_path / 'mod.py', 'foo', 'nonexistent') is None


def test_suggest_extract_nested_function_with_parent_params(tmp_path: Path) -> None:
    """suggest_extract returns candidate when nested uses only parent's params."""
    code = "def long_foo(x):\n    def inner():\n        a = x\n        b = x + 1\n        return a + b\n    return inner()\n"
    (tmp_path / 'mod.py').write_text(code)
    sugg = suggest_extract_nested_function(tmp_path / 'mod.py', 'long_foo')
    assert sugg is not None
    assert sugg[0] == 'inner'
    assert sugg[2] == ['x']


def test_extract_nested_function_with_extra_params(tmp_path: Path) -> None:
    """extract_nested_function with extra_params adds them to signature and call site."""
    code = "def long_foo(x):\n    def inner():\n        a = x\n        return a\n    return inner()\n"
    (tmp_path / 'mod.py').write_text(code)
    result = extract_nested_function(tmp_path / 'mod.py', 'long_foo', 'inner', extra_params=['x'])
    assert result is not None
    (tmp_path / 'mod.py').write_text(result)
    content = (tmp_path / 'mod.py').read_text()
    assert 'def inner(x):' in content or 'def inner(x ):' in content or 'def inner( x):' in content
    assert 'return inner(x)' in content


def test_suggest_extract_nested_function_with_parent_locals_up_to_three(tmp_path: Path) -> None:
    """suggest_extract returns candidate when nested uses up to 3 parent locals."""
    code = """
def long_foo(flag):
    x = 1
    y = 2
    def inner():
        if flag:
            return x + y
        return x
    return inner()
"""
    (tmp_path / "mod.py").write_text(code)
    sugg = suggest_extract_nested_function(tmp_path / "mod.py", "long_foo")
    assert sugg is not None
    assert sugg[0] == "inner"
    assert sugg[2] == ["flag", "x", "y"]


def test_extract_nested_function_with_parent_locals_extra_params(tmp_path: Path) -> None:
    """extract_nested_function accepts extra params derived from parent locals."""
    code = """
def long_foo():
    x = 10
    y = 20
    def inner():
        total = x + y
        return total
    return inner()
"""
    (tmp_path / "mod.py").write_text(code)
    sugg = suggest_extract_nested_function(tmp_path / "mod.py", "long_foo")
    assert sugg is not None
    nested_name, _, extra = sugg
    assert nested_name == "inner"
    assert extra == ["x", "y"]
    out = extract_nested_function(tmp_path / "mod.py", "long_foo", nested_name, extra_params=extra)
    assert out is not None
    (tmp_path / "mod.py").write_text(out)
    content = (tmp_path / "mod.py").read_text()
    assert "def inner(x, y):" in content
    assert "return inner(x, y)" in content


def test_extract_nested_function_uses_correct_parent_context(tmp_path: Path) -> None:
    """Extraction should target the requested parent, not another nested context with same helper name."""
    code = """
def target_parent():
    def helper():
        return 1
    return helper()

def other_parent():
    def helper():
        return 2
    return helper()
"""
    (tmp_path / "mod.py").write_text(code)
    result = extract_nested_function(tmp_path / "mod.py", "target_parent", "helper")
    assert result is not None
    (tmp_path / "mod.py").write_text(result)
    content = (tmp_path / "mod.py").read_text()
    assert content.count("def helper():") == 2
    assert "return helper()" in content
    assert content.index("def helper():") < content.index("def target_parent():")


# --- deep_nesting: extract_block_to_helper ---


def test_suggest_extract_block_finds_deep_if(tmp_path: Path) -> None:
    """suggest_extract_block returns helper_name, block_line, line_count, extra_params."""
    code = """
def foo(x):
    if x > 0:
        if x < 10:
            a = x + 1
            b = a * 2
            c = b + x
            d = c * 2
            e = d + 1
    return 0
"""
    (tmp_path / "mod.py").write_text(code)
    r = suggest_extract_block(tmp_path / "mod.py", "foo")
    assert r is not None
    helper_name, block_line, line_count, extra = r
    assert "_extracted_block_" in helper_name
    assert block_line >= 1
    assert line_count >= 5
    assert extra == ["x"]


def test_suggest_extract_block_skips_when_block_calls_extracted_helper(tmp_path: Path) -> None:
    """suggest_extract_block returns None when block already calls _extracted_block_* (avoid recursion)."""
    code = """
def _extracted_block_39(x):
    return x + 1

def foo(x):
    result = 0
    if x > 0:
        if x < 10:
            result = _extracted_block_39(x)
    return result
"""
    (tmp_path / "mod.py").write_text(code)
    r = suggest_extract_block(tmp_path / "mod.py", "foo", min_lines=3)
    assert r is None


def test_extract_block_to_helper_skips_block_with_extracted_call(tmp_path: Path) -> None:
    """extract_block_to_helper returns None when target block contains _extracted_block_* (avoid recursion)."""
    code = """
def _extracted_block_39(x):
    return x + 1

def foo(x):
    result = 0
    if x > 0:
        if x < 10:
            result = _extracted_block_39(x)
    return result
"""
    (tmp_path / "mod.py").write_text(code)
    # block_start_line=10 would match "if x > 0" whose body contains the call
    out = extract_block_to_helper(
        tmp_path / "mod.py", "foo", block_start_line=10,
        helper_name="_extracted_block_10", extra_params=["x"],
    )
    assert out is None


def test_suggest_extract_block_skips_when_return_in_block(tmp_path: Path) -> None:
    """suggest_extract_block returns None when block has return/break/continue."""
    code = """
def foo(x):
    if x > 0:
        if x < 10:
            return x
    return 0
"""
    (tmp_path / "mod.py").write_text(code)
    r = suggest_extract_block(tmp_path / "mod.py", "foo")
    assert r is None


def test_extract_block_to_helper_reduces_nesting(tmp_path: Path) -> None:
    """extract_block_to_helper moves block to helper and replaces with call."""
    code = """
def foo(x):
    if x > 0:
        if x < 10:
            a = x + 1
            b = a * 2
            c = b + x
            d = c * 2
            result = d
    return 0
"""
    (tmp_path / "mod.py").write_text(code)
    r = suggest_extract_block(tmp_path / "mod.py", "foo", min_lines=3)
    assert r is not None
    helper_name, block_line, _, extra = r
    out = extract_block_to_helper(
        tmp_path / "mod.py", "foo", block_line, helper_name, extra
    )
    assert out is not None
    (tmp_path / "mod.py").write_text(out)
    content = (tmp_path / "mod.py").read_text()
    assert f"def {helper_name}" in content
    assert f"{helper_name}(x)" in content or f"{helper_name}( x)" in content


def test_extract_block_to_helper_returns_value_when_block_assigns_to_outer(tmp_path: Path) -> None:
    """extract_block_to_helper adds return+assignment when block assigns to parent local."""
    code = """
def foo(x):
    result = 0
    if x > 0:
        if x < 10:
            a = x + 1
            b = a * 2
            c = b + x
            d = c * 2
            result = d
    return result
"""
    (tmp_path / "mod.py").write_text(code)
    r = suggest_extract_block(tmp_path / "mod.py", "foo", min_lines=5)
    assert r is not None
    helper_name, block_line, _, extra = r
    out = extract_block_to_helper(
        tmp_path / "mod.py", "foo", block_line, helper_name, extra
    )
    assert out is not None
    (tmp_path / "mod.py").write_text(out)
    ns: dict = {}
    exec(compile((tmp_path / "mod.py").read_text(), "mod.py", "exec"), ns)
    assert ns["foo"](5) == 34, "foo(5): a=6,b=12,c=17,d=34 => result=34"
    assert "result = " in (tmp_path / "mod.py").read_text()
    assert "return " in (tmp_path / "mod.py").read_text()


def test_extract_block_to_helper_returns_value_from_try_except_assign(tmp_path: Path) -> None:
    """try/except that assigns outer local must become return + call-site assign (not bare call)."""
    code = """
def match_fuzzy(sim_cfg, default=0.7):
    threshold = default
    if sim_cfg is None:
        threshold = default
    elif sim_cfg is not None:
        try:
            threshold = float(sim_cfg)
        except (TypeError, ValueError):
            threshold = default
    return threshold
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    # Target the elif body (try/except) — last stmt is Try, not Assign.
    out = extract_block_to_helper(
        path,
        "match_fuzzy",
        block_start_line=7,
        helper_name="_extracted_block_7",
        extra_params=["sim_cfg", "default"],
    )
    assert out is not None, "extract must succeed for try/except assign"
    assert "threshold = _extracted_block_7(" in out
    assert "return threshold" in out or "return float(sim_cfg)" in out
    # Must not leave a discarded helper call.
    tree = ast.parse(out)
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id.startswith("_extracted_block_"):
                raise AssertionError(f"bare call to {func.id} discards return value")
    path.write_text(out)
    ns: dict = {}
    exec(compile(out, "mod.py", "exec"), ns)
    assert ns["match_fuzzy"]("0.8") == 0.8
    assert ns["match_fuzzy"]("bad") == 0.7
    assert ns["match_fuzzy"](None) == 0.7


def test_extract_block_preserves_surrounding_formatting(tmp_path: Path) -> None:
    """Surgical splice must not rewrite quotes/layout outside the extracted region."""
    code = '''
def _uses_completion_tokens(model: str) -> bool:
    """Reasoning/gpt-oss models treat max_tokens as a prompt cap and return empty content."""
    key = (model or "").lower()
    return "gpt-oss" in key or key.startswith("o1")


def _call_litellm(prompt: str, max_tokens: int = 350) -> tuple[str | None, str | None]:
    api_key = None
    base = "https://example.com"
    model = "gpt"
    kwargs: dict[str, object] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "timeout": 60.0,
    }
    if base:
        # Other OpenAI-compatible hosts (Cerebras, Gemini OpenAI bridge, …).
        kwargs["model"] = model if str(model).startswith("openai/") else f"openai/{str(model).split('/')[-1]}"
        kwargs["api_base"] = base
        if api_key:
            kwargs["api_key"] = api_key
    return None, None
'''
    path = tmp_path / "architect_like.py"
    path.write_text(code)
    out = extract_block_to_helper(
        path,
        "_call_litellm",
        block_start_line=16,
        helper_name="_extracted_block_16",
        extra_params=["api_key", "base", "kwargs", "model"],
    )
    assert out is not None
    assert 'key = (model or "").lower()' in out
    assert '"gpt-oss" in key' in out
    assert 'kwargs: dict[str, object] = {' in out
    assert "_extracted_block_16(api_key, base, kwargs, model)" in out
    assert out.count('"""') >= 2  # docstring kept
    # Must not flip surrounding double quotes wholesale.
    assert "return 'gpt-oss'" not in out


def test_suggest_extract_block_skips_single_call_wrapper(tmp_path: Path) -> None:
    """Do not propose extract that only wraps one existing call."""
    code = """
def try_review_in_approvals_call(tools, session, *, name, arguments, call_id):
    return True

def _dispatch_tool_calls(runtime, session, name, arguments, call_id):
    if name in {"agent_edit", "git_commit", "git_push"}:
        handled = try_review_in_approvals_call(
            runtime.tools,
            session,
            name=name,
            arguments=arguments,
            call_id=call_id,
        )
        return handled
    return False
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    assert suggest_extract_block(path, "_dispatch_tool_calls", min_lines=5) is None
    assert (
        extract_block_to_helper(
            path,
            "_dispatch_tool_calls",
            block_start_line=8,
            helper_name="_extracted_block_8",
            extra_params=["arguments", "call_id", "name", "runtime", "session"],
        )
        is None
    )


def test_extract_block_refuses_outer_augassign(tmp_path: Path) -> None:
    code = """
def settle_teacher(now, rows, sample, i, n_exp, MATCH_WINDOW_MS):
    ts = int(sample.get("ts") or 0)
    if now - ts > MATCH_WINDOW_MS:
        expired = dict(sample)
        expired["settled"] = True
        expired["skip"] = True
        expired["expired"] = True
        rows[i] = expired
        n_exp += 1
        changed = True
    return n_exp, changed
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    out = extract_block_to_helper(
        path,
        "settle_teacher",
        block_start_line=4,
        helper_name="_extracted_block_4",
        extra_params=["i", "rows", "sample"],
    )
    assert out is None


def test_extract_block_mutates_via_loop_without_returning_loop_var(tmp_path: Path) -> None:
    """Inner for-target must not become return_var (would invent ``th = helper()``)."""
    code = """
def run_book_tick(now, opens, theses, filled):
    for pos in filled:
        opens.append(pos)
        for th in theses:
            if th.get("id") == pos.get("thesis_id"):
                th["status"] = "open"
                th["updated_ms"] = now
    return opens
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    out = extract_block_to_helper(
        path,
        "run_book_tick",
        block_start_line=3,
        helper_name="_extracted_block_4",
        extra_params=["now", "opens", "pos", "theses"],
    )
    assert out is not None
    assert "return th" not in out
    assert "th = _extracted_block_4" not in out
    assert "_extracted_block_4(now, opens, pos, theses)" in out
    # side-effect bare or no bogus assign
    assert "opens.append(pos)" in out

    code = """
import os
import subprocess
import time

def start_telegram_bot_background(cmd, log_f, root):
    try:
        log_f.write(f"\\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\\n")
        log_f.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except OSError as exc:
        return None
    return proc
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    assert suggest_extract_block(path, "start_telegram_bot_background", min_lines=5) is None
    assert (
        extract_block_to_helper(
            path,
            "start_telegram_bot_background",
            block_start_line=8,
            helper_name="_extracted_block_8",
            extra_params=["cmd", "log_f", "root"],
        )
        is None
    )


def test_suggest_extract_block_skips_status_bits_appends(tmp_path: Path) -> None:
    code = """
def format_self_check_for_chat(raw, verdict_bits):
    if "pytorch" in raw:
        low = raw.lower()
        if "available: yes" in low or "available:yes" in low.replace(" ", ""):
            verdict_bits.append("PyTorch available")
        if "cuda: no" in low or "device: cpu" in low:
            verdict_bits.append("inference on CPU")
        elif "cuda: yes" in low:
            verdict_bits.append("CUDA present")
    return verdict_bits
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    assert suggest_extract_block(path, "format_self_check_for_chat", min_lines=5) is None


def test_suggest_extract_block_skips_presentation_message_builder(tmp_path: Path) -> None:
    """Do not extract f-string status message builders into `_extracted_block_*`."""
    code = """
def run_direct_handlers(trained):
    if trained.get("ok"):
        acc = float(trained.get("train_accuracy") or 0)
        extra = (
            f"\\nRouter trained: samples={trained.get('samples')}, "
            f"classes={trained.get('classes')}, acc={acc:.3f}"
        )
        if acc < 0.5:
            extra += "\\nlow acc warning"
        return extra
    return ""
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    assert suggest_extract_block(path, "run_direct_handlers", min_lines=5) is None


def test_extract_block_to_helper_refuses_multi_outer_assigns(tmp_path: Path) -> None:
    """Refuse extract when block writes multiple parent locals (unsafe single return)."""
    code = """
def foo(x):
    a = 0
    b = 0
    if x > 0:
        a = x + 1
        b = x + 2
    return a + b
"""
    path = tmp_path / "mod.py"
    path.write_text(code)
    out = extract_block_to_helper(
        path, "foo", block_start_line=4, helper_name="_extracted_block_4", extra_params=["x"]
    )
    assert out is None


def test_extract_block_to_helper_supports_nested_parent_function(tmp_path: Path) -> None:
    """extract_block_to_helper works when parent function is nested inside another function."""
    code = """
def outer():
    def inner(node, depth):
        if depth > 0:
            if isinstance(node, int):
                a = node + 1
                b = a * 2
                c = b + depth
                d = c * 2
                value = d
        return 0
    return inner(1, 2)
"""
    (tmp_path / "mod.py").write_text(code)
    s = suggest_extract_block(tmp_path / "mod.py", "inner", min_lines=3)
    assert s is not None
    helper_name, block_line, _, extra = s
    out = extract_block_to_helper(tmp_path / "mod.py", "inner", block_line, helper_name, extra)
    assert out is not None
    (tmp_path / "mod.py").write_text(out)
    content = (tmp_path / "mod.py").read_text()
    assert f"def {helper_name}" in content
    assert f"{helper_name}(depth, node)" in content or f"{helper_name}(node, depth)" in content


def test_extract_block_to_helper_passes_loop_variable(tmp_path: Path) -> None:
    """extract_block_to_helper includes loop variable in extra_params for for-loop body."""
    code = '''
out = []
def process(items):
    for x in items:
        y = len(x)
        z = y + 1
        out.append(z)
'''
    (tmp_path / "mod.py").write_text(code)
    s = suggest_extract_block(tmp_path / "mod.py", "process", min_lines=3)
    assert s is not None, "for-loop body should be extractable"
    helper_name, block_line, _, extra = s
    assert "x" in extra, "loop variable x must be in extra_params"
    out = extract_block_to_helper(tmp_path / "mod.py", "process", block_line, helper_name, extra)
    assert out is not None
    (tmp_path / "mod.py").write_text(out)
    ns: dict = {}
    exec(compile((tmp_path / "mod.py").read_text(), "mod.py", "exec"), ns)
    ns["process"](["a", "bc"])
    assert ns["out"] == [2, 3], "len(a)+1=2, len(bc)+1=3"


def test_suggest_extract_block_includes_parent_body_locals(tmp_path: Path) -> None:
    """suggest_extract_block passes parent body locals (rows, report) as extra_params, not just params."""
    code = '''
def foo(items):
    rows = list(items)
    report = []
    for row in rows:
        a = row + 1
        b = a * 2
        report.append(b)
    return report
'''
    (tmp_path / "mod.py").write_text(code)
    r = suggest_extract_block(tmp_path / "mod.py", "foo", min_lines=3)
    assert r is not None
    _, _, _, extra = r
    assert "row" in extra, "loop var must be passed"
    assert "rows" in extra or "report" in extra, "parent body locals (rows or report) must be in extra_params"


def test_suggest_extract_block_skips_nested_parent_with_closure_dependencies(tmp_path: Path) -> None:
    """suggest_extract_block returns None when block depends on outer-scope closure vars."""
    code = """
def outer():
    parent_locals = {"x"}
    min_lines = 5
    def collect_blocks(node, depth):
        if isinstance(node, int):
            body = [node]
            used = set(body)
            assigned = set()
            used_from_outer = used - assigned & parent_locals
            if len(used_from_outer) >= min_lines:
                return True
        return False
    return collect_blocks(1, 0)
"""
    (tmp_path / "mod.py").write_text(code)
    out = suggest_extract_block(tmp_path / "mod.py", "collect_blocks", min_lines=3)
    assert out is None
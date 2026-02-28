"""Tests for eurika.refactor.extract_function (extract nested function, extract block to helper)."""
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
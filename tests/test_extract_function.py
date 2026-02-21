"""Tests for eurika.refactor.extract_function (extract nested function to module level)."""
from pathlib import Path
from eurika.refactor.extract_function import extract_nested_function, suggest_extract_nested_function

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
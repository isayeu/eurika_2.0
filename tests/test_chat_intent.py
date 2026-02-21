"""Tests for chat intent (ROADMAP 3.5.11.C)."""

def test_detect_intent_save() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('напиши factorial и сохрани в utils.py')
    assert intent == 'save'
    assert target and 'utils' in target

def test_detect_intent_save_to() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('save code to foo/bar.py')
    assert intent == 'save'
    assert 'bar' in (target or '')

def test_detect_intent_save_to_directory() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('сохрани в tests/ файл test_utils.py')
    assert intent == 'save'
    assert target == 'tests/test_utils.py'

def test_detect_intent_save_to_directory_english() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('save to tests/ bar.py')
    assert intent == 'save'
    assert target == 'tests/bar.py'

def test_detect_intent_refactor() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('рефактори architecture_planner.py')
    assert intent == 'refactor'
    assert target

def test_detect_intent_delete() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('удали test_factorial.py')
    assert intent == 'delete'
    assert 'test_factorial' in (target or '')

def test_detect_intent_delete_english() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('delete foo/bar.py')
    assert intent == 'delete'
    assert 'bar' in (target or '')

def test_detect_intent_create() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('создай пустой файл 111.txt')
    assert intent == 'create'
    assert target == '111.txt'

def test_detect_intent_create_english() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('create empty file foo/bar.txt')
    assert intent == 'create'
    assert 'bar' in (target or '')

def test_detect_intent_remember() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('Меня зовут Андрей, запомни это')
    assert intent == 'remember'
    assert target == 'name:Андрей'

def test_detect_intent_recall() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('как меня зовут?')
    assert intent == 'recall'
    assert target == 'name'

def test_detect_intent_none() -> None:
    from eurika.api.chat_intent import detect_intent
    intent, target = detect_intent('привет как дела')
    assert intent is None
    assert target is None

def test_extract_code_block() -> None:
    from eurika.api.chat_intent import extract_code_block
    text = 'Here you go:\n```python\ndef foo():\n    return 1\n```'
    code = extract_code_block(text)
    assert code
    assert 'def foo' in code
    assert 'return 1' in code

def test_extract_code_block_empty() -> None:
    from eurika.api.chat_intent import extract_code_block
    assert extract_code_block('no code here') is None
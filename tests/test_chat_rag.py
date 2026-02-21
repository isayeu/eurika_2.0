"""Tests for chat RAG (ROADMAP 3.5.11.B)."""
from pathlib import Path

def test_load_chat_pairs_empty(tmp_path: Path) -> None:
    from eurika.api.chat_rag import _load_chat_pairs
    assert _load_chat_pairs(tmp_path / 'nonexistent.jsonl') == []

def test_load_chat_pairs_skips_errors(tmp_path: Path) -> None:
    from eurika.api.chat_rag import _load_chat_pairs
    p = tmp_path / 'chat.jsonl'
    p.write_text('{"role":"user","content":"hello","ts":"x"}\n{"role":"assistant","content":"[Error] ollama down","ts":"y"}\n{"role":"user","content":"hi","ts":"z"}\n{"role":"assistant","content":"Hi there!","ts":"w"}\n', encoding='utf-8')
    pairs = _load_chat_pairs(p)
    assert len(pairs) == 1
    assert pairs[0][0] == 'hi' and pairs[0][1] == 'Hi there!'

def test_retrieve_similar_chats_no_history(tmp_path: Path) -> None:
    from eurika.api.chat_rag import retrieve_similar_chats
    (tmp_path / '.eurika' / 'chat_history').mkdir(parents=True)
    assert retrieve_similar_chats(tmp_path, 'hello', top_k=3) == []

def test_retrieve_similar_chats_finds_similar(tmp_path: Path) -> None:
    from eurika.api.chat_rag import retrieve_similar_chats
    chat_dir = tmp_path / '.eurika' / 'chat_history'
    chat_dir.mkdir(parents=True)
    chat_path = chat_dir / 'chat.jsonl'
    chat_path.write_text('{"role":"user","content":"write a fibonacci function","ts":"a"}\n{"role":"assistant","content":"def fib(n): return 1 if n<2 else fib(n-1)+fib(n-2)","ts":"b"}\n{"role":"user","content":"add tests","ts":"c"}\n{"role":"assistant","content":"def test_fib(): assert fib(5)==5","ts":"d"}\n', encoding='utf-8')
    results = retrieve_similar_chats(tmp_path, 'write fibonacci in python', top_k=2)
    assert len(results) >= 1
    assert 'fib' in results[0].get('assistant', '').lower()

def test_format_rag_examples_empty() -> None:
    from eurika.api.chat_rag import format_rag_examples
    assert format_rag_examples([]) == ''

def test_format_rag_examples_one() -> None:
    from eurika.api.chat_rag import format_rag_examples
    out = format_rag_examples([{'user': 'hi', 'assistant': 'Hello!'}])
    assert 'User: hi' in out
    assert 'Assistant: Hello!' in out
    assert 'Similar past exchanges' in out
# Shelved modules (v0.2+)

Эти модули не используются в v0.1 observe-only:

- agent_core.py
- agent_runtime.py
- reasoner_dummy.py
- selector.py
- executor_sandbox.py

Они остаются в корне проекта (для импортов memory.py). Не вызываются из main.

**v0.1 entry point:** `python eurika_cli.py scan [path]`

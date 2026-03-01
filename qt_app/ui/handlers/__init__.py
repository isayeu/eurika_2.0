"""Event handlers for MainWindow. Reduces main_window.py size (ROADMAP 3.1-arch.3)."""
from . import approve_handlers, chat_handlers, command_handlers, dashboard_handlers, ollama_handlers

__all__ = [
    "approve_handlers",
    "chat_handlers",
    "command_handlers",
    "dashboard_handlers",
    "ollama_handlers",
]

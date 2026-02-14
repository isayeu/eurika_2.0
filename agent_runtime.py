"""
Agent Runtime v0.2

Minimal executable loop:
Input → Context → DummyReasoner → Selector → ExecutorSandbox → Memory

This is a *living* minimal agent.
No AI. No LLM. Full determinism. Full traceability.
"""

from agent_core import AgentCore, InputEvent
from memory import SimpleMemory
from reasoner_dummy import DummyReasoner
from selector import SimpleSelector
from executor_sandbox import ExecutorSandbox


class EurikaRuntime:
    def __init__(self):
        self.memory = SimpleMemory()
        self.reasoner = DummyReasoner()
        self.selector = SimpleSelector()
        self.executor = ExecutorSandbox()
        self.agent = AgentCore(
            memory=self.memory,
            reasoner=self.reasoner,
            selector=self.selector,
            executor=self.executor,
        )

    def run_cli(self):
        print("Eurika Agent v0.2 — Sandbox Runtime")
        print("Commands: 'analyze' / 'scan' — code analysis | 'exit' — quit")

        while True:
            user_input = input("› ").strip()
            if user_input.lower() in {"exit", "quit"}:
                break

            event = InputEvent(type="user_text", payload=user_input)
            result = self.agent.step(event)

            status = "OK" if result.success else "FAIL"
            message = result.output.get("error", result.output.get("payload", result.output))
            print(f"→ {status}: {message}")


if __name__ == "__main__":
    EurikaRuntime().run_cli()

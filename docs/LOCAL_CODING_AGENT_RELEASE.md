# Eurika local coding agent: release gate

The VS Code/VSCodium extension is the primary coding UI. The Qt application
remains available for Market, Approvals, and operational panels; it is not the
primary coding-agent transport.

## Automated integration matrix

- Protocol handshake and capability negotiation:
  `tests/test_local_agent_backend.py`.
- Session creation, model response events, structured read calls, approval
  boundaries, and continuation after tool results:
  `tests/test_local_agent_backend.py`.
- Workspace traversal and symlink confinement:
  `tests/test_local_agent_backend.py`.
- Ignore-aware lexical/symbol retrieval:
  `tests/test_local_agent_backend.py`.
- Cancellation, timeout containment, and stdio framing:
  `tests/test_local_agent_backend.py`.
- NDJSON request/response, cancellation frames, and backend-crash rejection:
  `vscode-extension/test/protocol.test.ts`.
- Mention/rule parsing and conflict-safe checkpoint decisions:
  `vscode-extension/test/pure.test.ts`.
- Type safety and extension bundle:
  `npm --prefix vscode-extension run check` and
  `npm --prefix vscode-extension test`.

## Dogfood eval set

`tests/fixtures/local_agent_eval_cases.json` defines the first stable task set:
project questions, symbol retrieval, a focused verified fix, a multi-file
change, and rollback conflict handling. Case IDs and required tool contracts
are validated by the Python test suite.

For each dogfood run, record:

- whether the task succeeded after diagnostics/tests;
- tool-call count and tool-call errors;
- whether supplied context contained the evidence used in the answer;
- model/tool latency;
- approval rejection and checkpoint rollback outcomes.

The backend emits per-turn `latencyMs`, `toolCalls`, `toolCallErrors`,
`contextBytes`, and `verified` metrics. The extension mirrors these records to
the Eurika output channel.

## Manual release checks

Before packaging a VSIX:

1. Ask a project question and verify a streamed, source-grounded answer.
2. Cancel a slow request, restart the backend, and send another message.
3. Request a two-file edit; preview and resolve each file independently.
4. Apply the proposal, run verification, and confirm the model receives the
   structured result before responding.
5. Restore the checkpoint. Confirm later user edits are reported as conflicts,
   never overwritten.
6. Confirm an untrusted workspace cannot start the backend or mutate files.
7. Confirm terminal tools remain disabled by default and require explicit
   approval when enabled.

Release is blocked by a hung process, an edit outside the workspace, an
unreviewed mutation, lost user content during restore, or a claimed successful
verification without a structured diagnostics/test result.

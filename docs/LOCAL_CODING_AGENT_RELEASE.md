# Eurika local coding agent: release gate

Eurika Desktop is the standalone primary coding UI. The VS Code/VSCodium
extension is an optional adapter to the same Python core. Qt remains available
during migration; it is not the primary coding-agent transport.

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
- Cross-client manifests, core-owned proposals/checkpoints, and product panels:
  `tests/test_local_agent_backend.py`.
- Electron sandbox/preload boundary:
  `npm --prefix eurika-desktop test`.
- Standalone sidecar dogfood:
  `npm --prefix eurika-desktop run dogfood`.
  Covers workspace list, proposal apply, per-file apply of a two-file
  change, clean checkpoint restore, restore conflict on a later user edit,
  terminal/command, git_commit, and git_push refused without explicit
  approval, shared Approvals (apply-approved)/Commands/Context (Diff/Apply for dialog_state)/Market panel state, structured
  diagnostics after apply, cancellation of an in-flight terminal tool, and
  idle-self-dev prefs/status (Qt↔Desktop shared opt-in; no LLM propose in dogfood),
  product `chat/send` («модель себя») and `mentions/suggest`,
  Models panel (`panel/state models`; prefs writes require approval).
  Requires `@eurika/client` build output under `clients/eurika-client/lib/`
  (`npm --prefix clients/eurika-client run build`; predogfood runs this).
- Desktop type safety and production bundle:
  `npm --prefix eurika-desktop run check` and
  `npm --prefix eurika-desktop run build`.

## Dogfood eval set

`tests/fixtures/local_agent_eval_cases.json` defines the first stable task set:
project questions, symbol retrieval, a focused verified fix, a multi-file
change, rollback conflict handling, and `git-hitl-commit` (git_commit without
approval must fail). Case IDs and required tool contracts are validated by the
Python test suite.

CR-H (Chat one-loop, ROADMAP §5.4.1) adds product eval — same core, live Chat
or HTTP `POST /api/chat` with `client_terminal_text` (not a hidden Cursor
shell):

- already-ran: user says they ran a check in Terminal and asks if it failed;
  the model must cite the attached pane / last_check and must not spawn
  pytest or `release_check.sh`.
- follow-up «исправь» uses that sealed log, not a stale successful mypy.
- after H2: Qt Chat Send and Desktop Agent Send share one runtime class
  (no `wants_local_agent` split). Imperative «прогони release check» must
  start the script immediately (not a lecture about skill/H2).
- H3: a docs/plan question must not become the last_check lecture
  («say исправь»). «исправь» still uses the sealed log.
- H4: Desktop has one Send (`chat/send`). There is no Eurika vs Agent
  toggle. `session/chat` is only for HITL toolResults continuation.
  Live `POST /api/chat` on the gateway uses the same dispatch (not a
  raw `chat_send` file-list dump).
- H5: while a turn runs, Qt and Desktop Chat show an expandable Thinking
  row in the thread (tool / ritual / Model rounds from `live_activity`).
  A 600s silent bubble is a fail. Token-level model stream is still open.

Qt and Desktop coding path (same core): `reviewInApprovals` parks edits into
Approvals; both clients auto-focus that tab when `approvalsQueued > 0`. Missing
agent HTTP for a Qt coding request fails loudly (no silent core-chat fallback).
Covered by `tests/test_qt_agent_hitl.py` and
`tests/test_local_agent_backend.py` (`client: desktop`).

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

Before packaging Desktop or a VSIX:

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
8. Open Approvals, Commands, Market, and Models in Desktop and verify they read the same
   project state as Qt (Models: routing/status only; no secret values).
9. Build Linux artifacts in an Ubuntu LTS image and launch them on the oldest
   supported glibc baseline.
10. CR-H: run a quality check in the Terminal pane, then ask Chat whether it
    failed — the answer must use that output and must not start a second
    full pytest / release_check. Restart `eurika-qt` after backend routing
    changes (module cache).
11. CR-H2/H5: «прогони release check» in Chat starts the script (Thinking
    expands with steps). Desktop must not dump `[API]` assistant lines for
    agent progress. «hello» replies briefly and does not dump last_check
    or ROADMAP. Do not leave the UI on «Eurika печатает…» with no steps.

Release is blocked by a hung process, an edit outside the workspace, an
unreviewed mutation, lost user content during restore, or a claimed successful
verification without a structured diagnostics/test result.

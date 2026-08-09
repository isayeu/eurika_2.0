# Eurika Local Agent for VS Code/VSCodium

This directory contains the editor client for Eurika's local coding-agent protocol. It starts a configurable Python child process, communicates over newline-delimited JSON-RPC 2.0, and keeps code access and mutations inside VS Code's trusted workspace APIs.

## Development

Requirements: Node.js 20+, npm, VS Code or VSCodium 1.90+, and a Python backend implementing the protocol below.

```sh
npm install
npm run check
npm test
```

Open this directory in VS Code and launch an Extension Development Host with `--extensionDevelopmentPath` pointing here, or package `dist/extension.js` with your preferred VSIX tooling. The default backend command is:

```text
python -m eurika.agent.stdio
```

Override `eurika.backend.command`, `eurika.backend.args`, or `eurika.backend.cwd` when the backend has a different entry point. The process is never launched in an untrusted workspace.

## User workflow

- Open the Eurika activity-bar view, select a model, and send a prompt. Responses stream into the sidebar and can be cancelled.
- Add explicit context with `@file:path/to/file.py` or `@folder:path/to/folder`. Quoted paths support spaces.
- Use **Eurika: Explain Selection**, **Fix Selection or Diagnostics**, and **Generate Tests** from the editor menu or Command Palette.
- Backend edit calls are staged as multi-file proposals. Inspect files in VS Code's diff editor, then apply or reject the proposal.
- Every apply stores a bounded workspace checkpoint. **Eurika: Restore Last Checkpoint** restores only files that still match Eurika's applied content; later user changes are reported as conflicts and never overwritten.
- Rules under `.eurika/rules/**/*.{md,mdc}` are sent with context. Optional frontmatter supports `alwaysApply: true` and `glob`/`globs`.

Terminal tools are disabled by default. Enable `eurika.tools.allowTerminal` to permit them; every command still requires a modal confirmation. Test requests use VS Code's Test Results UI.

## Protocol contract

Each JSON-RPC object occupies one UTF-8 line. The extension sends:

- `initialize` with protocol version, client/workspace information, and client capabilities.
- `session/chat` with `sessionId`, model, user message, editor context, diagnostics, diff, rules, and explicit mentions.
- `session/cancel` when the user cancels.
- `session/chat` continuation with structured `toolResults` after an approved action.

The backend returns the `initialize` capability object (`protocolVersion`, `models`, and `tools`), answers `session/chat`, and emits `agent/event` notifications. Recognized event types include `message_start`, `response/chunk`, `message_end`, and structured tool lifecycle events. Mutating calls returned as `pendingToolCalls` are routed through editor review or an explicit run confirmation. Their structured results are sent back through `session/chat` so the model can verify and correct its work.

Supported structured tools:

- `search`: `{ query, glob?, limit? }`
- `read`: `{ path|uri, startLine?, endLine? }`
- `edit`: `{ edits: [{ path|uri, newText?, range? }], preview? }`
- `diagnostics`: `{ path|uri? }`
- `git_diff`: `{ staged? }`
- `terminal`: `{ command, name? }`
- `tests`: `{}`

Edits are not silently applied. The `edit` result has `status: "awaiting_user_approval"` and a transaction ID used by the sidebar.

The release and dogfood matrix is documented in `../docs/LOCAL_CODING_AGENT_RELEASE.md`.

## Safety and persistence

The extension passes selection, active/open documents, diagnostics, Git diff, and bounded mention content to the local process. Context is capped by `eurika.context.maxBytes`. File reads and edits are constrained to the workspace, common generated/vendor directories are excluded, and process stderr is available in the Eurika output channel.

The current session, selected model, chat history, and the latest 20 checkpoints use VS Code workspace state. Child processes receive `SIGTERM` on deactivation/restart and are force-stopped after a short grace period.

Pure protocol, mention/rule, hashing, and conflict-detection helpers are tested with Node's built-in test runner and do not require a VS Code host.

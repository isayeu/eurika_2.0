# Eurika Desktop

Standalone Electron shell for the Eurika Python core. VS Code and Qt remain
optional adapters; product logic stays behind the versioned JSON-RPC API.

## Development

```bash
npm install
npm run check
npm test
npm run dogfood
EURIKA_PYTHON=/path/to/python npm start
```

The desktop opens a workspace, starts `python -m eurika.agent.stdio`, and offers
Monaco editing, Chat, structured tools, diff approvals, checkpoints, terminal
commands, Approvals, Context (dialog_state Diff/Apply/Reject), Commands, and Market panels.

The header provides **Refresh files** and conflict-safe **Restore checkpoint**.
Backend startup/crash details are shown in the red error banner and mirrored to
the integrated terminal.

Chat history is restored from the workspace-scoped Eurika history when the
Desktop restarts. **Clear** removes that persisted context for all clients of
the current workspace.

After an agent edit is applied or rejected, Desktop sends the structured
decision back to the same session so the model can continue with verification
and a final answer.

Terminal and test requests use the same loop: Desktop shows the exact structured
arguments, waits for **Run** or **Reject**, mirrors output to the terminal, and
returns the decision to the model.

## Linux package

```bash
npm run dist:linux
```

Build release artifacts in an Ubuntu LTS CI image (currently the oldest
supported glibc baseline), not on the newest rolling distribution. The MVP uses
an installed Eurika Python environment selected with `EURIKA_PYTHON`; bundling a
signed Python sidecar is a later distribution task.

Security defaults: renderer sandbox, context isolation, no Node integration,
deny-by-default permissions, a narrow preload bridge, workspace-confined Python
tools, and explicit approval for edits, commands, tests, and restores.

Qt also exposes **Открыть Eurika Desktop** next to the project selector and
passes the selected workspace automatically. The button uses the unpacked
package only when that binary is newer than Desktop sources; otherwise it
falls back to `npm start` so a stale build cannot hide local UI work.

To install a Linux application menu shortcut after packaging:

```bash
bash eurika-desktop/scripts/install-linux-launcher.sh
```

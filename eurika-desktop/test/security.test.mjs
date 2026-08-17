import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const main = await readFile(new URL("../electron/main.ts", import.meta.url), "utf8");
const preload = await readFile(new URL("../electron/preload.ts", import.meta.url), "utf8");
const renderer = await readFile(new URL("../src/main.ts", import.meta.url), "utf8");
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");

test("desktop renderer is isolated from Node", () => {
  assert.match(main, /contextIsolation:\s*true/);
  assert.match(main, /nodeIntegration:\s*false/);
  assert.match(main, /sandbox:\s*true/);
  assert.match(main, /setPermissionRequestHandler/);
});

test("preload exposes a narrow bridge instead of ipcRenderer", () => {
  assert.match(preload, /contextBridge\.exposeInMainWorld\("eurika"/);
  assert.doesNotMatch(preload, /exposeInMainWorld\([^]*ipcRenderer\s*[,}]/);
  assert.match(main, /REQUEST_METHODS\.has\(method\)/);
});

test("late backend events cannot target a destroyed window", () => {
  assert.match(main, /target\.isDestroyed\(\)/);
  assert.match(main, /target\.webContents\.isDestroyed\(\)/);
  assert.match(main, /window = undefined/);
});

test("desktop exposes refresh, restore, and visible backend errors", () => {
  assert.match(html, /id="refresh-files"/);
  assert.match(html, /id="checkpoint-select"/);
  assert.match(html, /id="restore-checkpoint"/);
  assert.match(html, /id="error-banner"/);
  assert.match(renderer, /"checkpoint\/list"/);
  assert.match(renderer, /"checkpoint\/restore"/);
  assert.match(renderer, /showError\(error\)/);
  assert.doesNotMatch(renderer, /statusElement\.textContent = "error"/);
});

test("desktop restores workspace chat history through the core", () => {
  assert.match(html, /id="clear-chat"/);
  assert.match(main, /"session\/history"/);
  assert.match(main, /"session\/clear"/);
  assert.match(renderer, /restoreChatHistory/);
  assert.match(renderer, /messagesElement\.replaceChildren\(\)/);
});

test("approved or rejected edits continue the model tool-loop", () => {
  assert.match(renderer, /currentPendingCall/);
  assert.match(renderer, /toolResults:/);
  assert.match(renderer, /decision: apply \? "applied" : "rejected"/);
  assert.match(renderer, /await renderChatResult\(continuation\)/);
});

test("terminal and test tools require an explicit Desktop decision", () => {
  assert.match(renderer, /function renderToolApproval/);
  assert.match(renderer, /function decideToolApproval/);
  assert.match(renderer, /arguments: \{ \.\.\.\(call\.arguments \?\? \{\}\), approval: true \}/);
  assert.match(renderer, /status: "rejected"/);
  assert.match(renderer, /Resolve the pending/);
});

test("sidecar dogfood covers independent apply, restore conflict, and terminal approval", async () => {
  const dogfood = await readFile(new URL("../scripts/dogfood.mjs", import.meta.url), "utf8");
  assert.match(dogfood, /paths: \["alpha\.txt"\]/);
  assert.match(dogfood, /later user-edit conflict/);
  assert.match(dogfood, /code === -32001/);
  assert.match(dogfood, /panel\/state/);
  assert.match(dogfood, /structured diagnostics/);
  assert.match(dogfood, /AbortController/);
});

test("desktop requires folder trust before starting the backend", () => {
  assert.match(main, /Trust folder/);
  assert.match(main, /trusted-workspaces\.json/);
  assert.match(main, /untrusted: true/);
  assert.match(renderer, /Trust this folder to start Eurika/);
});

test("desktop can cancel an in-flight chat request", () => {
  assert.match(html, /id="cancel-chat"/);
  assert.match(preload, /eurika:cancel/);
  assert.match(main, /eurika:cancel/);
  assert.match(main, /controller\.signal/);
  assert.match(renderer, /function cancelChat/);
  assert.match(renderer, /agent\/event/);
});

test("desktop panes stay inside the window and scroll internally", async () => {
  const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
  assert.match(css, /grid-template-columns:\s*minmax\(0,\s*280px\)\s*minmax\(0,\s*1fr\)\s*minmax\(0,\s*360px\)/);
  assert.match(css, /#agent-pane \{[\s\S]*min-height:\s*0/);
  assert.match(css, /#product-panel, #messages \{[\s\S]*overflow:\s*auto/);
  assert.match(css, /#prompt \{[\s\S]*min-width:\s*0/);
  assert.match(css, /#terminal \{[\s\S]*overflow:\s*hidden/);
  assert.match(css, /#chat-form \{[\s\S]*display:\s*grid/);
  assert.match(renderer, /ResizeObserver\(fitTerminal\)/);
});

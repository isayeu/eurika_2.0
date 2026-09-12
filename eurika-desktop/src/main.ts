import * as monaco from "monaco-editor";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import "./styles.css";
import { ancestorFolders, buildFileTree, type FileTreeNode } from "./file-tree";

type ToolResult<T> = { result: T };
type ProposalFile = {
  path: string;
  before?: string | null;
  after?: string | null;
};
type Proposal = { proposalId: string; files: ProposalFile[] };
type PendingCall = {
  callId: string;
  tool: string;
  arguments?: Record<string, unknown>;
  proposal?: Proposal;
};
type ChatResult = {
  text?: string;
  error?: string;
  pendingToolCalls?: PendingCall[];
  approvalsQueued?: number;
  terminal_cmd?: string;
  terminal_output?: string;
  open_project?: string;
};

const filesElement = required("files");
const tabsElement = required("tabs");
const messagesElement = required("messages");
const proposalElement = required("proposal");
const productPanel = required("product-panel");
const workspaceElement = required("workspace");
const statusElement = required("status");
const errorBanner = required("error-banner");
const checkpointSelect = required("checkpoint-select") as HTMLSelectElement;
const cancelChatButton = required("cancel-chat") as HTMLButtonElement;
const sendChatButton = required("send-chat") as HTMLButtonElement;
const editorHost = required("editor");
const terminalHost = required("terminal");
const terminal = new Terminal({ convertEol: true, theme: { background: "#111318" } });
const fit = new FitAddon();
terminal.loadAddon(fit);
terminal.open(terminalHost);
const fitTerminal = (): void => {
  if (terminalHost.clientWidth < 8 || terminalHost.clientHeight < 8) return;
  fit.fit();
};
new ResizeObserver(fitTerminal).observe(terminalHost);
requestAnimationFrame(fitTerminal);

let editor: monaco.editor.IStandaloneCodeEditor | undefined;
let diffEditor: monaco.editor.IStandaloneDiffEditor | undefined;
let activePath: string | undefined;
let activeVersion: string | undefined;
let loadedContent: string | undefined;
let currentProposal: Proposal | undefined;
let currentPendingCall: PendingCall | undefined;
let currentProposalSelection = new Set<string>();
let chatRequestId: string | undefined;
let streamMessage: HTMLElement | undefined;
let thinkingSteps: string[] = [];
let fileTree: FileTreeNode[] = [];
const activeToolCalls = new Map<string, { tool: string; arguments?: Record<string, unknown> }>();
const expandedFolders = new Set<string>();
const seenChatKeys = new Set<string>();
const seenActivityKeys = new Set<string>();
let activityOffset = 0;
let livePollTimer: number | undefined;
let idleSelfDevTimer: number | undefined;
let idleSelfDevBusy = false;
const IDLE_SELF_DEV_POLL_MS = 60_000;

function chatKey(role: string, text: string): string {
  return `${role}:${text.trim().slice(0, 800)}`;
}

function rememberChat(role: string, text: string): boolean {
  const key = chatKey(role, text);
  if (seenChatKeys.has(key)) return false;
  seenChatKeys.add(key);
  return true;
}

function required(id: string): HTMLElement {
  const value = document.getElementById(id);
  if (!value) throw new Error(`Missing #${id}`);
  return value;
}

function showError(error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  errorBanner.textContent = message;
  errorBanner.hidden = false;
  document.body.classList.add("error-visible");
}

function clearError(): void {
  errorBanner.hidden = true;
  errorBanner.textContent = "";
  document.body.classList.remove("error-visible");
}

async function runUi(action: () => Promise<void>): Promise<void> {
  clearError();
  try {
    await action();
  } catch (error) {
    showError(error);
  }
}

function showEditor(content: string, path: string): void {
  diffEditor?.dispose();
  diffEditor = undefined;
  if (!editor) {
    editor = monaco.editor.create(editorHost, {
      automaticLayout: true,
      minimap: { enabled: false },
      theme: "vs-dark",
    });
  }
  const old = editor.getModel();
  const model = monaco.editor.createModel(content, languageFor(path), monaco.Uri.file(path));
  editor.setModel(model);
  loadedContent = content;
  old?.dispose();
}

function showDiff(file: ProposalFile): void {
  editor?.dispose();
  editor = undefined;
  diffEditor?.dispose();
  diffEditor = monaco.editor.createDiffEditor(editorHost, {
    automaticLayout: true,
    readOnly: true,
    theme: "vs-dark",
  });
  diffEditor.setModel({
    original: monaco.editor.createModel(file.before ?? "", languageFor(file.path)),
    modified: monaco.editor.createModel(file.after ?? "", languageFor(file.path)),
  });
}

function languageFor(path: string): string {
  if (path.endsWith(".py")) return "python";
  if (path.endsWith(".ts") || path.endsWith(".tsx")) return "typescript";
  if (path.endsWith(".js")) return "javascript";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".md")) return "markdown";
  return "plaintext";
}

async function openWorkspace(requested?: string): Promise<void> {
  const result = await window.eurika.initialize(requested);
  if (result.cancelled) return;
  if (result.untrusted) {
    workspaceElement.textContent = "untrusted";
    throw new Error("Trust this folder to start Eurika. The backend was not started.");
  }
  workspaceElement.textContent = String(result.workspace ?? "");
  seenChatKeys.clear();
  seenActivityKeys.clear();
  activityOffset = 0;
  await restoreChatHistory();
  await refreshFiles();
  startLiveFollow();
  await syncIdleSelfDevFromPrefs();
}

async function restoreChatHistory(): Promise<void> {
  const history = await window.eurika.request<{
    messages: Array<{ role: string; content: string }>;
  }>("session/history", { limit: 80 });
  messagesElement.replaceChildren();
  seenChatKeys.clear();
  for (const message of history.messages) {
    appendMessage(message.role, message.content);
  }
}

function startLiveFollow(): void {
  if (livePollTimer !== undefined) window.clearInterval(livePollTimer);
  livePollTimer = window.setInterval(() => {
    void pollLiveActivity();
  }, 800);
}

async function pollLiveActivity(): Promise<void> {
  try {
    const activity = await window.eurika.request<{
      events: Array<{
        id?: string;
        phase?: string;
        client?: string;
        title?: string;
        method?: string;
        kind?: string;
        text?: string;
        terminal_cmd?: string;
        terminal_output?: string;
        error?: string;
        ok?: boolean;
        approvalsQueued?: number;
      }>;
      offset: number;
    }>("activity/recent", { afterOffset: activityOffset, limit: 80 });
    activityOffset = activity.offset;
    for (const event of activity.events ?? []) {
      const key = `${event.id ?? ""}:${event.phase ?? ""}`;
      if (seenActivityKeys.has(key)) continue;
      seenActivityKeys.add(key);
      const isSelfDev =
        event.client === "idle_self_dev" || event.method === "idle_self_dev";
      const title = event.title || event.method || "API";
      if (event.client === "agent" && event.kind !== "http") {
        if (event.phase === "progress" || event.phase === "start") {
          appendThinking(title);
        }
        continue;
      }
      if (event.phase === "start" || event.phase === "progress" || event.kind === "http") {
        if (isSelfDev) {
          const line = title.startsWith("саморазвитие") ? title : `[саморазвитие] ${title}`;
          terminal.writeln(line);
        } else {
          appendThinking(title);
        }
      }
      if (event.phase === "done" && isSelfDev) {
        const doneText = (event.text || title || "").trim();
        if (doneText) {
          const line = doneText.startsWith("саморазвитие")
            ? doneText
            : `[саморазвитие] ${doneText}`;
          appendMessage("assistant", line);
        }
        if ((event.approvalsQueued ?? 0) > 0) {
          void runUi(() => showPanel("approvals"));
        } else {
          void runUi(() => showPanel("context"));
        }
      }
      if (event.terminal_cmd) terminal.writeln(event.terminal_cmd);
      if (event.terminal_output) terminal.writeln(event.terminal_output);
      if (event.error && !isSelfDev) appendMessage("assistant", `[API error] ${event.error}`);
    }
    const history = await window.eurika.request<{
      messages: Array<{ role: string; content: string }>;
    }>("session/history", { limit: 80 });
    for (const message of history.messages) {
      if (seenChatKeys.has(chatKey(message.role, message.content))) continue;
      appendMessage(message.role, message.content);
    }
  } catch {
    // Backend may be restarting; the next tick retries.
  }
}

async function syncIdleSelfDevFromPrefs(): Promise<void> {
  const box = required("idle-self-dev") as HTMLInputElement;
  try {
    const prefs = await window.eurika.request<{ idle_self_dev?: boolean }>(
      "idle-self-dev/prefs",
    );
    box.checked = Boolean(prefs.idle_self_dev);
  } catch {
    box.checked = false;
  }
  syncIdleSelfDevTimer();
}

function syncIdleSelfDevTimer(): void {
  const box = required("idle-self-dev") as HTMLInputElement;
  if (!box.checked) {
    if (idleSelfDevTimer !== undefined) {
      window.clearInterval(idleSelfDevTimer);
      idleSelfDevTimer = undefined;
    }
    return;
  }
  if (idleSelfDevTimer === undefined) {
    idleSelfDevTimer = window.setInterval(() => {
      void pollIdleSelfDev();
    }, IDLE_SELF_DEV_POLL_MS);
  }
  void pollIdleSelfDev();
}

async function pollIdleSelfDev(): Promise<void> {
  const box = required("idle-self-dev") as HTMLInputElement;
  if (!box.checked || idleSelfDevBusy || chatRequestId) return;
  idleSelfDevBusy = true;
  try {
    const result = await window.eurika.request<{
      skipped?: string | null;
      message?: string;
      approvalsQueued?: number;
      ok?: boolean;
    }>("idle-self-dev/run");
    if (result.skipped) return;
    if ((result.approvalsQueued ?? 0) > 0) {
      void runUi(() => showPanel("approvals"));
    }
  } catch (error) {
    appendMessage(
      "assistant",
      `саморазвитие: ${error instanceof Error ? error.message : String(error)}`,
    );
  } finally {
    idleSelfDevBusy = false;
  }
}

async function clearChatHistory(): Promise<void> {
  if (!window.confirm("Clear persisted chat history for this workspace?")) return;
  await window.eurika.request("session/clear");
  messagesElement.replaceChildren();
  seenChatKeys.clear();
}

async function refreshFiles(): Promise<void> {
  const result = await window.eurika.request<{ files: string[] }>("workspace/list");
  fileTree = buildFileTree(result.files);
  renderFileTree();
  await refreshCheckpoints();
}

function renderFileTree(): void {
  filesElement.replaceChildren();
  appendTreeNodes(fileTree, 0);
}

function appendTreeNodes(nodes: FileTreeNode[], depth: number): void {
  for (const node of nodes) {
    if (node.kind === "folder") {
      const expanded = expandedFolders.has(node.path);
      const row = document.createElement("button");
      row.type = "button";
      row.className = `tree-row folder${expanded ? " open" : ""}`;
      row.style.paddingLeft = `${8 + depth * 12}px`;
      row.title = node.path;
      row.setAttribute("aria-expanded", expanded ? "true" : "false");
      const twist = document.createElement("span");
      twist.className = "tree-twist";
      twist.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.className = "tree-label";
      label.textContent = node.name;
      row.append(twist, label);
      row.onclick = () => {
        if (expandedFolders.has(node.path)) expandedFolders.delete(node.path);
        else expandedFolders.add(node.path);
        renderFileTree();
      };
      filesElement.append(row);
      if (expanded) appendTreeNodes(node.children, depth + 1);
      continue;
    }
    const row = document.createElement("button");
    row.type = "button";
    row.className = `tree-row file${activePath === node.path ? " active" : ""}`;
    row.style.paddingLeft = `${20 + depth * 12}px`;
    row.title = node.path;
    row.textContent = node.name;
    row.onclick = () => void runUi(() => openFile(node.path));
    filesElement.append(row);
  }
}

async function refreshCheckpoints(): Promise<void> {
  const listed = await window.eurika.request<{
    checkpoints: Array<{ id: string; paths: string[]; createdAt?: string }>;
  }>("checkpoint/list");
  const selected = checkpointSelect.value;
  checkpointSelect.replaceChildren();
  for (const checkpoint of [...listed.checkpoints].reverse()) {
    const option = document.createElement("option");
    option.value = checkpoint.id;
    option.textContent = `${checkpoint.id} (${checkpoint.paths.length} files)`;
    checkpointSelect.append(option);
  }
  if (!listed.checkpoints.length) {
    checkpointSelect.append(new Option("No checkpoints", ""));
  } else if ([...checkpointSelect.options].some((option) => option.value === selected)) {
    checkpointSelect.value = selected;
  }
}

async function restoreCheckpoint(): Promise<void> {
  const checkpointId = checkpointSelect.value;
  if (!checkpointId) throw new Error("No Eurika checkpoint is available");
  const listed = await window.eurika.request<{
    checkpoints: Array<{ id: string; paths: string[] }>;
  }>("checkpoint/list");
  const checkpoint = listed.checkpoints.find((item) => item.id === checkpointId);
  if (!checkpoint) throw new Error(`Checkpoint ${checkpointId} no longer exists`);
  if (!window.confirm(`Restore checkpoint ${checkpoint.id} for ${checkpoint.paths.length} file(s)?`)) {
    return;
  }
  if (
    activePath &&
    checkpoint.paths.includes(activePath) &&
    editor &&
    loadedContent !== undefined &&
    editor.getValue() !== loadedContent
  ) {
    throw new Error(`Save or discard unsaved changes in ${activePath} before restore`);
  }
  const result = await window.eurika.request<{
    restored: string[];
    conflicts: string[];
  }>("checkpoint/restore", {
    checkpointId: checkpoint.id,
    approval: true,
  });
  appendMessage(
    "assistant",
    `Restored ${result.restored.length} file(s)` +
      (result.conflicts.length ? `; conflicts: ${result.conflicts.join(", ")}` : ""),
  );
  await refreshFiles();
  if (activePath && result.restored.includes(activePath)) await openFile(activePath);
}

async function openFile(path: string): Promise<void> {
  const response = await window.eurika.request<ToolResult<{
    content: string;
    version: string;
  }>>("tool/call", { tool: "read", arguments: { path } });
  activePath = path;
  activeVersion = response.result.version;
  for (const folder of ancestorFolders(path)) expandedFolders.add(folder);
  renderFileTree();
  tabsElement.replaceChildren();
  const name = document.createElement("span");
  name.textContent = path;
  const propose = document.createElement("button");
  propose.textContent = "Review save";
  propose.onclick = () => void runUi(proposeEditorSave);
  tabsElement.append(name, propose);
  showEditor(response.result.content, path);
}

async function proposeEditorSave(): Promise<void> {
  if (!activePath || !editor) return;
  const descriptor = await window.eurika.request<Proposal>("proposal/prepare", {
    path: activePath,
    content: editor.getValue(),
    expectedVersion: activeVersion,
  });
  renderProposal(await hydrateProposal(descriptor));
}

function appendMessage(role: string, text: string): HTMLElement {
  rememberChat(role, text);
  const item = document.createElement("div");
  item.className = `message ${role}`;
  const label = document.createElement("strong");
  label.textContent = role === "user" ? "You" : role === "thinking" ? "Thinking" : "Eurika";
  const body = document.createElement("p");
  body.textContent = text;
  item.append(label, body);
  messagesElement.append(item);
  messagesElement.scrollTop = messagesElement.scrollHeight;
  return item;
}

function thinkingPanel(): HTMLDetailsElement {
  return required("chat-thinking") as HTMLDetailsElement;
}

function formatThinkingStep(raw: string): string {
  let text = raw.replace(/^Thinking(?:\s*·\s*|\s+)/, "").trim();
  if (/^модель\b/i.test(text)) {
    return text.replace(/^модель\s*/i, "Model").trim() || "Model";
  }
  const mapping: Array<[RegExp, string]> = [
    [/^read /i, "Read "],
    [/^search /i, "Grepped "],
    [/^edit /i, "Edited "],
    [/^skill /i, "Running "],
    [/^tests /i, "Tests "],
    [/^terminal /i, "Terminal "],
  ];
  for (const [re, label] of mapping) {
    if (re.test(text)) return text.replace(re, label);
  }
  return text;
}

function beginThinking(): void {
  thinkingSteps = [];
  const panel = thinkingPanel();
  required("chat-thinking-steps").textContent = "";
  panel.hidden = false;
  panel.open = true;
  if (streamMessage) streamMessage.before(panel);
  else messagesElement.append(panel);
}

function appendThinking(raw: string): void {
  const text = formatThinkingStep(raw);
  if (!text || thinkingSteps[thinkingSteps.length - 1] === text) return;
  thinkingSteps.push(text);
  const panel = thinkingPanel();
  required("chat-thinking-steps").textContent = thinkingSteps.join("\n");
  panel.hidden = false;
  panel.open = true;
  if (streamMessage && panel.parentElement !== messagesElement) {
    streamMessage.before(panel);
  }
}

function finishThinking(): void {
  const panel = thinkingPanel();
  if (thinkingSteps.length) {
    const parked = panel.cloneNode(true) as HTMLDetailsElement;
    parked.removeAttribute("id");
    parked.querySelector("#chat-thinking-steps")?.removeAttribute("id");
    parked.open = false;
    parked.hidden = false;
    parked.classList.add("message", "thinking");
    panel.before(parked);
  }
  thinkingSteps = [];
  required("chat-thinking-steps").textContent = "";
  panel.hidden = true;
  panel.open = false;
  proposalElement.before(panel);
}

function setChatBusy(busy: boolean, cancellable = true): void {
  cancelChatButton.disabled = !(busy && cancellable);
  sendChatButton.disabled = busy;
}

function updateStream(text: string): void {
  const body = streamMessage?.querySelector("p");
  if (body) body.textContent = text;
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

function extractAtToken(text: string, cursor: number): { at: number; prefix: string } | null {
  const pos = Math.max(0, Math.min(cursor, text.length));
  const before = text.slice(0, pos);
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  if (at > 0) {
    const prev = before[at - 1] ?? "";
    if (/[A-Za-z0-9_./\-]/.test(prev)) return null;
  }
  const prefix = before.slice(at + 1);
  if (!/^[A-Za-z0-9_./\-]*$/.test(prefix)) return null;
  return { at, prefix };
}

function mentionPopup(): HTMLUListElement {
  return required("mention-popup") as HTMLUListElement;
}

function hideMentionPopup(): void {
  const popup = mentionPopup();
  popup.hidden = true;
  popup.replaceChildren();
}

function insertMention(input: HTMLTextAreaElement, name: string): void {
  const token = extractAtToken(input.value, input.selectionStart ?? input.value.length);
  if (!token) return;
  const cursor = input.selectionStart ?? input.value.length;
  const next = `${input.value.slice(0, token.at)}@${name} ${input.value.slice(cursor)}`;
  const pos = token.at + name.length + 2;
  input.value = next;
  input.setSelectionRange(pos, pos);
  hideMentionPopup();
  input.focus();
}

function bindMentionInput(input: HTMLTextAreaElement): void {
  const popup = mentionPopup();
  let selected = 0;
  const items = (): HTMLLIElement[] => [...popup.querySelectorAll("li")];

  const render = async (): Promise<void> => {
    const token = extractAtToken(input.value, input.selectionStart ?? input.value.length);
    if (!token) {
      hideMentionPopup();
      return;
    }
    const result = await window.eurika.request<{ candidates?: string[] }>("mentions/suggest", {
      prefix: token.prefix,
      limit: 12,
    });
    const candidates = Array.isArray(result.candidates) ? result.candidates : [];
    if (!candidates.length) {
      hideMentionPopup();
      return;
    }
    popup.replaceChildren();
    candidates.forEach((name, index) => {
      const li = document.createElement("li");
      li.textContent = name;
      li.setAttribute("aria-selected", index === 0 ? "true" : "false");
      li.onmousedown = (event) => {
        event.preventDefault();
        insertMention(input, name);
      };
      popup.append(li);
    });
    selected = 0;
    popup.hidden = false;
  };

  input.addEventListener("input", () => {
    void render();
  });
  input.addEventListener("click", () => {
    void render();
  });
  input.addEventListener("keydown", (event) => {
    if (popup.hidden) return;
    const rows = items();
    if (!rows.length) return;
    if (event.key === "Escape") {
      event.preventDefault();
      hideMentionPopup();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      selected = event.key === "ArrowDown"
        ? (selected + 1) % rows.length
        : (selected - 1 + rows.length) % rows.length;
      rows.forEach((row, index) => {
        row.setAttribute("aria-selected", index === selected ? "true" : "false");
      });
      rows[selected]?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (event.key === "Tab" || event.key === "Enter") {
      const name = rows[selected]?.textContent;
      if (name) {
        event.preventDefault();
        insertMention(input, name);
      }
    }
  });
}

async function sendChat(message: string): Promise<void> {
  if (currentPendingCall) {
    throw new Error(`Resolve the pending ${currentPendingCall.tool} action first`);
  }
  if (chatRequestId) {
    throw new Error("A chat request is already running");
  }
  appendMessage("user", message);
  streamMessage = appendMessage("assistant", "…");
  beginThinking();
  appendThinking("печатает…");
  const requestId = `chat-${Date.now()}`;
  chatRequestId = requestId;
  setChatBusy(true);
  try {
    const result = await window.eurika.request<ChatResult>("chat/send", {
      message,
      context: chatAgentContext(),
    }, requestId);
    const text = String(result.text ?? result.error ?? "");
    updateStream(text);
    if (result.terminal_cmd) terminal.writeln(String(result.terminal_cmd));
    if (result.terminal_output) terminal.writeln(String(result.terminal_output));
    if (result.open_project) {
      terminal.writeln(`[open_project] ${result.open_project} — Open workspace to switch`);
    }
    await renderChatResult(result, { skipText: true });
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    updateStream(text);
    if (!/cancel/i.test(text)) throw error;
  } finally {
    if (chatRequestId === requestId) chatRequestId = undefined;
    streamMessage = undefined;
    finishThinking();
    setChatBusy(false);
  }
}

async function cancelChat(): Promise<void> {
  if (!chatRequestId) return;
  await window.eurika.cancel(chatRequestId);
}

async function renderChatResult(result: ChatResult, options: { skipText?: boolean } = {}): Promise<void> {
  if (!options.skipText) appendMessage("assistant", String(result.text ?? result.error ?? ""));
  const edit = result.pendingToolCalls?.find((call) => call.proposal);
  if (edit?.proposal) renderProposal(await hydrateProposal(edit.proposal), edit);
  for (const call of result.pendingToolCalls ?? []) {
    if (call.tool !== "edit") {
      renderToolApproval(call);
    }
  }
  // Qt parity: park agent_edit in Approvals; refresh Context when visible.
  if ((result.approvalsQueued ?? 0) > 0) {
    await showPanel("approvals");
  } else if (!productPanel.hidden && productPanel.dataset.activePanel === "context") {
    await showPanel("context");
  }
}

function chatAgentContext(): { activeFile?: string; reviewInApprovals: true; client: "desktop" } {
  return { activeFile: activePath, reviewInApprovals: true, client: "desktop" };
}

function renderToolApproval(call: PendingCall): void {
  currentProposal = undefined;
  currentPendingCall = call;
  proposalElement.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = `Approval required: ${call.tool}`;
  const details = document.createElement("pre");
  if (call.tool === "git_commit") {
    const message = String(call.arguments?.message ?? "").trim() || "(empty message)";
    const paths = Array.isArray(call.arguments?.paths)
      ? (call.arguments?.paths as unknown[]).map((item) => String(item))
      : [];
    details.textContent = [`message: ${message}`, `paths: ${paths.length ? paths.join(", ") : "(safe dirty files)"}`].join("\n");
  } else if (call.tool === "git_push") {
    details.textContent = "Push current branch to origin.\nNever --force / --force-with-lease.";
  } else {
    details.textContent = JSON.stringify(call.arguments ?? {}, null, 2);
  }
  const approve = document.createElement("button");
  approve.textContent =
    call.tool === "tests" ? "Run tests" : call.tool === "git_commit" ? "Commit" : call.tool === "git_push" ? "Push" : "Run approved";
  approve.onclick = () => void runUi(() => decideToolApproval(true));
  const reject = document.createElement("button");
  reject.textContent = "Reject";
  reject.onclick = () => void runUi(() => decideToolApproval(false));
  proposalElement.append(heading, details, approve, reject);
}

async function decideToolApproval(approved: boolean): Promise<void> {
  const call = currentPendingCall;
  if (!call || call.tool === "edit") return;
  let result: unknown = { status: "rejected" };
  if (approved) {
    const execution = await window.eurika.request<ToolResult<Record<string, unknown>>>(
      "tool/call",
      {
        callId: call.callId,
        tool: call.tool,
        arguments: { ...(call.arguments ?? {}), approval: true },
      },
    );
    result = execution.result;
    const stdout = String(execution.result.stdout ?? "");
    const stderr = String(execution.result.stderr ?? "");
    if (stdout) terminal.write(stdout);
    if (stderr) terminal.write(`\x1b[31m${stderr}\x1b[0m`);
    if ("exitCode" in execution.result) {
      terminal.writeln(`\r\n[exit ${String(execution.result.exitCode)}]`);
    }
  }
  currentPendingCall = undefined;
  proposalElement.replaceChildren();
  appendMessage("assistant", approved ? `${call.tool} completed.` : `${call.tool} rejected.`);
  const continuation = await window.eurika.request<ChatResult>("session/chat", {
    toolResults: [{ callId: call.callId, tool: call.tool, result }],
    context: chatAgentContext(),
  });
  await renderChatResult(continuation);
}

async function hydrateProposal(descriptor: Proposal): Promise<Proposal> {
  const files: ProposalFile[] = [];
  for (const file of descriptor.files) {
    const result = await window.eurika.request<Proposal>("proposal/get", {
      proposalId: descriptor.proposalId,
      path: file.path,
    });
    files.push(result.files[0]);
  }
  return { proposalId: descriptor.proposalId, files };
}

function selectedProposalPaths(proposal: Proposal): string[] {
  const picked = proposal.files
    .map((file) => file.path)
    .filter((path) => currentProposalSelection.has(path));
  return picked.length ? picked : proposal.files.map((file) => file.path);
}

function renderReadOnlyDiff(title: string, text: string): void {
  if (currentProposal) return;
  proposalElement.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = title;
  const details = document.createElement("pre");
  details.textContent = text.trim() || "(clean)";
  proposalElement.append(heading, details);
}

function renderProposal(proposal: Proposal, pendingCall?: PendingCall): void {
  currentProposal = proposal;
  currentPendingCall = pendingCall;
  currentProposalSelection = new Set(proposal.files.map((file) => file.path));
  proposalElement.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = `Proposed changes (${proposal.files.length})`;
  proposalElement.append(heading);
  for (const file of proposal.files) {
    const row = document.createElement("div");
    row.className = "proposal-row";
    const pick = document.createElement("input");
    pick.type = "checkbox";
    pick.checked = true;
    pick.onchange = () => {
      if (pick.checked) currentProposalSelection.add(file.path);
      else currentProposalSelection.delete(file.path);
    };
    const preview = document.createElement("button");
    preview.textContent = file.path;
    preview.onclick = () => {
      if (
        file.path === activePath &&
        editor &&
        loadedContent !== undefined &&
        editor.getValue() !== loadedContent &&
        editor.getValue() !== file.after
      ) {
        appendMessage("assistant", `Save or discard unsaved changes in ${file.path} first.`);
        return;
      }
      showDiff(file);
    };
    row.append(pick, preview);
    proposalElement.append(row);
  }
  const apply = document.createElement("button");
  apply.textContent = "Apply selected";
  apply.onclick = () => void runUi(() => decideProposal(true));
  const reject = document.createElement("button");
  reject.textContent = "Reject selected";
  reject.onclick = () => void runUi(() => decideProposal(false));
  proposalElement.append(apply, reject);
  const first = proposal.files.find((file) => currentProposalSelection.has(file.path)) ?? proposal.files[0];
  const dirtyConflict =
    first.path === activePath &&
    editor &&
    loadedContent !== undefined &&
    editor.getValue() !== loadedContent &&
    editor.getValue() !== first.after;
  if (dirtyConflict) {
    const warning = document.createElement("p");
    warning.textContent = `Unsaved editor changes block preview/apply for ${first.path}.`;
    proposalElement.append(warning);
  } else {
    showDiff(first);
  }
}

async function decideProposal(apply: boolean): Promise<void> {
  if (!currentProposal) return;
  const proposalId = currentProposal.proposalId;
  const pendingCall = currentPendingCall;
  const selected = selectedProposalPaths(currentProposal);
  if (!selected.length) throw new Error("Select at least one file in the proposal first");
  let outcome: { applied?: string[]; rejected?: string[]; remaining?: string[] };
  if (apply) {
    const activeProposal = currentProposal.files.find((file) => file.path === activePath);
    if (
      activeProposal &&
      editor &&
      loadedContent !== undefined &&
      editor.getValue() !== loadedContent &&
      editor.getValue() !== activeProposal.after
    ) {
      throw new Error(`Save or discard the dirty editor buffer before applying ${activePath}`);
    }
    outcome = await window.eurika.request("proposal/apply", { proposalId, paths: selected, approval: true });
  } else {
    outcome = await window.eurika.request("proposal/reject", { proposalId, paths: selected });
  }
  await refreshFiles();
  if (activePath) await openFile(activePath);
  const remaining = Array.isArray(outcome.remaining) ? outcome.remaining : [];
  if (remaining.length) {
    const actioned = apply ? (outcome.applied ?? []).length : (outcome.rejected ?? []).length;
    appendMessage(
      "assistant",
      apply
        ? `Applied ${actioned} file(s). ${remaining.length} file(s) remain in the proposal.`
        : `Rejected ${actioned} file(s). ${remaining.length} file(s) remain in the proposal.`,
    );
    const refreshed = await hydrateProposal({
      proposalId,
      files: remaining.map((path) => ({ path })),
    });
    renderProposal(refreshed, pendingCall);
    return;
  }
  currentProposal = undefined;
  currentPendingCall = undefined;
  currentProposalSelection.clear();
  proposalElement.replaceChildren();
  appendMessage("assistant", apply ? "Changes applied. A restore checkpoint was created." : "Changes rejected.");
  if (pendingCall) {
    const continuation = await window.eurika.request<ChatResult>("session/chat", {
      toolResults: [
        {
          callId: pendingCall.callId,
          tool: pendingCall.tool,
          result: { decision: apply ? "applied" : "rejected", outcome },
        },
      ],
      context: chatAgentContext(),
    });
    await renderChatResult(continuation);
  }
}

function tokenize(command: string): string[] {
  return [...command.matchAll(/"([^"]*)"|'([^']*)'|([^\s]+)/g)].map(
    (match) => match[1] ?? match[2] ?? match[3],
  );
}

async function runTerminal(command: string): Promise<void> {
  const argv = tokenize(command);
  if (!argv.length) return;
  terminal.writeln(`\x1b[36m$ ${command}\x1b[0m`);
  const response = await window.eurika.request<ToolResult<{
    stdout: string;
    stderr: string;
    exitCode: number;
  }>>("tool/call", { tool: "terminal", arguments: { argv, approval: true } });
  if (response.result.stdout) terminal.write(response.result.stdout);
  if (response.result.stderr) terminal.write(`\x1b[31m${response.result.stderr}\x1b[0m`);
  terminal.writeln(`\r\n[exit ${response.result.exitCode}]`);
}

/** Qt Diff-gate: Apply only after preview for this fingerprint (auto-preview counts). */
let contextDiffSeenFp = "";

async function showPanel(panel: string): Promise<void> {
  if (panel === "chat") {
    productPanel.hidden = true;
    messagesElement.hidden = false;
    productPanel.dataset.activePanel = "";
    return;
  }
  const response = await window.eurika.request<{
    panel: string;
    data?: Record<string, unknown>;
    text?: string;
    note?: string;
    llm?: Record<string, unknown>;
    ml?: Record<string, unknown>;
    commands?: Array<{ id: string; requiresApproval: boolean }>;
    planValid?: boolean;
    planStale?: boolean;
    token?: string;
    fingerprint?: string;
    preview?: Record<string, unknown> | null;
    hasPendingGit?: boolean;
    hasPendingHostAdmin?: boolean;
    hostAdmin?: { commands?: string[]; preview?: string } | null;
    canReject?: boolean;
    canApply?: boolean;
  }>("panel/state", { panel });
  messagesElement.hidden = true;
  productPanel.hidden = false;
  productPanel.dataset.activePanel = panel;
  productPanel.replaceChildren();
  if (panel === "context") renderContext(response);
  if (panel === "approvals") renderApprovals(response.data ?? {});
  if (panel === "commands") renderCommands(response.commands ?? []);
  if (panel === "market") renderMarket(response.data ?? {});
  if (panel === "models") renderModels(response);
}

function renderContext(response: {
  text?: string;
  data?: Record<string, unknown>;
  planValid?: boolean;
  planStale?: boolean;
  token?: string;
  fingerprint?: string;
  preview?: Record<string, unknown> | null;
  hasPendingGit?: boolean;
  hasPendingHostAdmin?: boolean;
  hostAdmin?: { commands?: string[]; preview?: string } | null;
  canReject?: boolean;
  canApply?: boolean;
}): void {
  const text = response.text ?? "";
  const data = response.data ?? {};
  const fingerprint = String(response.fingerprint ?? "");
  const token = String(response.token ?? "");
  const planValid = Boolean(response.planValid);
  const planStale = Boolean(response.planStale);
  const canReject = Boolean(response.canReject);
  const canApplyBase = Boolean(response.canApply);
  const preview = response.preview && typeof response.preview === "object"
    ? response.preview
    : null;

  const title = document.createElement("h3");
  title.textContent = "Context";
  const pre = document.createElement("pre");
  pre.className = "context-panel";
  pre.textContent = text.trim() || "Нет активной цели и итога.";
  productPanel.append(title, pre);

  const hint = document.createElement("p");
  hint.className = "muted";
  hint.textContent =
    "dialog_state / host-admin HITL (не Approvals JSON). Diff → Apply, как в Qt Контекст.";
  productPanel.append(hint);

  const diffTitle = document.createElement("h4");
  diffTitle.textContent = "Pending Diff";
  const diffPre = document.createElement("pre");
  diffPre.className = "context-diff";
  const diffText = formatContextPreview(
    preview,
    data,
    Boolean(response.hasPendingGit),
    Boolean(response.hasPendingHostAdmin),
    response.hostAdmin,
  );
  diffPre.textContent = diffText;
  productPanel.append(diffTitle, diffPre);

  if (fingerprint && diffText && !diffText.startsWith("No pending")) {
    contextDiffSeenFp = fingerprint;
  } else if (!fingerprint) {
    contextDiffSeenFp = "";
  }

  const actions = document.createElement("div");
  actions.className = "context-actions";
  const diffBtn = document.createElement("button");
  diffBtn.textContent = "Diff";
  diffBtn.disabled = !(
    planValid
    || planStale
    || Boolean(response.hasPendingGit)
    || Boolean(response.hasPendingHostAdmin)
  );
  const applyBtn = document.createElement("button");
  applyBtn.textContent = "Apply";
  const rejectBtn = document.createElement("button");
  rejectBtn.textContent = "Reject";
  rejectBtn.disabled = !canReject;

  const syncApply = (): void => {
    const seen = Boolean(fingerprint) && contextDiffSeenFp === fingerprint;
    applyBtn.disabled = !(canApplyBase && !planStale && seen);
    applyBtn.title = applyBtn.disabled
      ? (planStale ? "Plan expired — Reject to clear" : "Сначала Diff")
      : "Apply pending plan (Diff уже просмотрен)";
  };
  syncApply();

  diffBtn.onclick = () => void runUi(async () => {
    const refreshed = await window.eurika.request<{
      fingerprint?: string;
      preview?: Record<string, unknown> | null;
      planValid?: boolean;
      planStale?: boolean;
      hasPendingGit?: boolean;
      hasPendingHostAdmin?: boolean;
      hostAdmin?: { commands?: string[]; preview?: string } | null;
    }>("context/preview", {});
    const fp = String(refreshed.fingerprint ?? fingerprint);
    const body = formatContextPreview(
      refreshed.preview && typeof refreshed.preview === "object" ? refreshed.preview : null,
      data,
      Boolean(refreshed.hasPendingGit),
      Boolean(refreshed.hasPendingHostAdmin),
      refreshed.hostAdmin,
    );
    diffPre.textContent = body;
    if (fp && body && !body.startsWith("No pending")) {
      contextDiffSeenFp = fp;
    }
    syncApply();
    terminal.writeln("[context] Diff refreshed");
  });

  applyBtn.onclick = () => void runUi(async () => {
    if (fingerprint && contextDiffSeenFp !== fingerprint) {
      terminal.writeln("[context] Сначала Diff — Apply после preview");
      return;
    }
    const result = await window.eurika.request<{
      ok?: boolean;
      text?: string;
      error?: string;
    }>("context/decide", {
      decision: "apply",
      token,
      approval: true,
    });
    terminal.writeln(`[context apply] ${String(result.text ?? result.error ?? "")}`);
    await showPanel("context");
  });

  rejectBtn.onclick = () => void runUi(async () => {
    const result = await window.eurika.request<{
      ok?: boolean;
      text?: string;
      error?: string;
    }>("context/decide", { decision: "reject" });
    contextDiffSeenFp = "";
    terminal.writeln(`[context reject] ${String(result.text ?? result.error ?? "")}`);
    await showPanel("context");
  });

  actions.append(diffBtn, applyBtn, rejectBtn);
  productPanel.append(actions);
}

function formatContextPreview(
  preview: Record<string, unknown> | null,
  data: Record<string, unknown>,
  hasPendingGit: boolean,
  hasPendingHostAdmin = false,
  hostAdmin?: { commands?: string[]; preview?: string } | null,
): string {
  if (preview) {
    const unified = String(preview.unified_diff ?? "").trim();
    if (unified) return unified;
    const err = String(preview.error ?? "").trim();
    if (err) {
      const intent = String(preview.intent ?? "");
      const target = String(preview.target ?? "");
      return [
        intent || target ? `intent=${intent || "-"} target=${target || "-"}` : "",
        err,
      ].filter(Boolean).join("\n");
    }
  }
  if (hasPendingGit) {
    const git = data.pending_git_commit;
    if (git && typeof git === "object") {
      const g = git as Record<string, unknown>;
      return `Pending git commit\ntoken=${String(g.token ?? "-")}\n\n${String(g.message ?? "")}`;
    }
  }
  if (hasPendingHostAdmin) {
    const previewText = String(hostAdmin?.preview ?? "").trim();
    if (previewText) return previewText;
    const cmds = Array.isArray(hostAdmin?.commands) ? hostAdmin.commands : [];
    if (cmds.length) {
      return ["Host admin HITL:", ...cmds.map((cmd) => `- ${cmd}`)].join("\n");
    }
  }
  return "No pending plan.";
}

function renderApprovals(data: Record<string, unknown>): void {
  const operations = Array.isArray(data.operations)
    ? data.operations.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    : [];
  const title = document.createElement("h3");
  title.textContent = `Approvals (${operations.length})`;
  productPanel.append(title);
  const hint = document.createElement("p");
  hint.className = "muted";
  hint.textContent =
    "`.eurika/pending_plan.json` (не dialog_state). Approve → Save или Run apply-approved.";
  productPanel.append(hint);
  const decisions: Array<{ index: number; select: HTMLSelectElement; operation: Record<string, unknown> }> = [];
  operations.forEach((operation, index) => {
    const row = document.createElement("div");
    row.className = "approval-row";
    const label = document.createElement("button");
    label.textContent = `${String(operation.target_file ?? "")} · ${String(operation.kind ?? "")}`;
    label.onclick = () => void runUi(async () => {
      const preview = await window.eurika.request<Record<string, unknown>>("approval/preview", { operation });
      terminal.writeln(String(preview.unified_diff ?? preview.error ?? "No diff"));
    });
    const select = document.createElement("select");
    for (const value of ["pending", "approve", "reject"]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.append(option);
    }
    select.value = String(operation.team_decision ?? "pending");
    row.append(label, select);
    productPanel.append(row);
    decisions.push({ index: index + 1, select, operation });
  });
  if (operations.length) {
    const actions = document.createElement("div");
    actions.className = "context-actions";
    const decisionPayload = () =>
      decisions.map(({ index, select, operation }) => ({
        index,
        team_decision: select.value,
        approved_by: "desktop-user",
        target_file: operation.target_file,
        kind: operation.kind,
      }));
    const save = document.createElement("button");
    save.textContent = "Save decisions";
    save.onclick = () => void runUi(async () => {
      const result = await window.eurika.request<Record<string, unknown>>("approval/save", {
        approval: true,
        operations: decisionPayload(),
      });
      terminal.writeln(`[approvals] ${JSON.stringify(result)}`);
    });
    const apply = document.createElement("button");
    apply.textContent = "Run apply-approved";
    apply.title = "Save row decisions, then eurika fix . --apply-approved";
    apply.onclick = () => void runUi(async () => {
      terminal.writeln("$ eurika fix . --apply-approved");
      const result = await window.eurika.request<Record<string, unknown>>("approval/apply", {
        approval: true,
        operations: decisionPayload(),
      });
      if (result.stdout) terminal.writeln(String(result.stdout));
      if (result.stderr) terminal.writeln(String(result.stderr));
      terminal.writeln(
        `[apply-approved exit ${String(result.exitCode ?? "?")}] saved=${JSON.stringify(result.saved ?? null)}`,
      );
      const applyText = String(result.text ?? "").trim();
      if (applyText) {
        appendMessage("assistant", applyText);
      } else {
        appendMessage(
          "assistant",
          `apply-approved (exit ${String(result.exitCode ?? "?")})`,
        );
      }
      await showPanel("approvals");
      void runUi(() => showPanel("context"));
    });
    actions.append(save, apply);
    productPanel.append(actions);
  } else if (data.error) {
    const err = document.createElement("p");
    err.className = "muted";
    err.textContent = String(data.error);
    productPanel.append(err);
  }
}

function renderCommands(commands: Array<{ id: string; requiresApproval: boolean }>): void {
  const title = document.createElement("h3");
  title.textContent = "Commands";
  productPanel.append(title);
  for (const command of commands) {
    const button = document.createElement("button");
    button.textContent = command.id;
    button.onclick = () => void runUi(async () => {
      terminal.writeln(`$ eurika ${command.id}`);
      const result = await window.eurika.request<Record<string, unknown>>("command/run", {
        command: command.id,
        approval: true,
      });
      terminal.writeln(String(result.stdout ?? ""));
      terminal.writeln(`[exit ${String(result.exitCode ?? "?")}]`);
    });
    productPanel.append(button);
  }
  const createBtn = document.createElement("button");
  createBtn.textContent = "init / scaffold";
  createBtn.title = "Sibling project: minimal | python | python-cli (HITL approval)";
  createBtn.onclick = () => void runUi(async () => {
    const name = window.prompt("Sibling project name", "my_app")?.trim();
    if (!name) return;
    const scaffoldRaw = window.prompt("Scaffold: minimal | python | python-cli", "python")?.trim()
      || "python";
    const scaffold = ["minimal", "python", "python-cli"].includes(scaffoldRaw)
      ? scaffoldRaw
      : "python";
    terminal.writeln(`$ project/create ${name} --scaffold ${scaffold}`);
    const result = await window.eurika.request<Record<string, unknown>>("project/create", {
      name,
      scaffold,
      approval: true,
    });
    terminal.writeln(String(result.text ?? result.error ?? JSON.stringify(result)));
    appendMessage("assistant", String(result.text ?? ""));
    await showPanel("context");
  });
  productPanel.append(createBtn);
}

function renderModels(state: {
  note?: string;
  llm?: Record<string, unknown>;
  ml?: Record<string, unknown>;
}): void {
  const llm = (state.llm ?? {}) as Record<string, unknown>;
  const ml = (state.ml ?? {}) as Record<string, unknown>;
  const ollama = (llm.ollama ?? {}) as { healthy?: boolean; models?: string[] };
  const torch = (ml.torch ?? {}) as Record<string, unknown>;
  const market = (ml.market ?? {}) as Record<string, unknown>;
  const keys = (llm.keys_present ?? {}) as Record<string, boolean>;
  const title = document.createElement("h3");
  title.textContent = "Models";
  const note = document.createElement("p");
  note.className = "muted";
  note.textContent = String(state.note ?? "Routing prefs + status. Keys stay in .env.");
  const form = document.createElement("div");
  form.className = "models-form";
  const provider = fieldSelect(
    "Provider",
    "models-provider",
    stringList(llm.providers, ["auto", "openai", "ollama", "cursor", "codex"]),
    String(llm.provider ?? "auto"),
  );
  const presets = Array.isArray(llm.presets) ? llm.presets : [];
  const presetIds = ["", ...presets.map((item) => String((item as { id?: string }).id ?? ""))];
  const presetLabels = [
    "from .env",
    ...presets.map((item) => {
      const preset = item as { id?: string; label?: string };
      return String(preset.label ?? preset.id ?? "");
    }),
  ];
  const preset = fieldSelect(
    "API preset",
    "models-preset",
    presetIds,
    String(llm.api_preset ?? ""),
    presetLabels,
  );
  const openaiModel = fieldInput("OpenAI model", "models-openai-model", String(llm.openai_model ?? ""));
  const ollamaModel = fieldInput("Ollama model", "models-ollama-model", String(llm.ollama_model ?? ""));
  const cursorModel = fieldInput("Cursor model", "models-cursor-model", String(llm.cursor_model ?? ""));
  const cursorRouter = fieldSelect(
    "Cursor router",
    "models-cursor-router",
    ["", "cost", "balanced", "intelligence"],
    String(llm.cursor_router ?? ""),
  );
  const timeout = fieldInput(
    "Timeout sec",
    "models-timeout",
    String(llm.timeout_sec ?? 120),
    "number",
  );
  const torchDevice = fieldSelect(
    "Torch device",
    "models-torch-device",
    stringList(ml.devices, ["cpu", "cuda", "mps"]),
    String(ml.torch_device ?? "cpu"),
  );
  form.append(
    ...provider,
    ...preset,
    ...openaiModel,
    ...ollamaModel,
    ...cursorModel,
    ...cursorRouter,
    ...timeout,
    ...torchDevice,
  );
  const status = document.createElement("p");
  status.className = "muted";
  status.textContent =
    `Ollama ${ollama.healthy ? "up" : "down"}` +
    `${ollama.models?.length ? ` · ${ollama.models.slice(0, 8).join(", ")}` : ""}` +
    ` · base ${String(llm.openai_base_url || "—")}` +
    ` · torch ${torch.available ? String(torch.version ?? "ok") : "off"}` +
    ` · paper trades ${String(market.trades ?? "—")}` +
    ` acc ${String(market.accuracy ?? "—")}` +
    ` live ${String(market.live_n ?? "—")}` +
    ` equity ${String(market.equity ?? "—")}` +
    ` opens ${String(market.opens ?? "—")}`;
  const keyRow = document.createElement("div");
  keyRow.className = "models-keys";
  for (const [name, present] of Object.entries(keys)) {
    const chip = document.createElement("span");
    chip.className = present ? "ok" : "";
    chip.textContent = `${name}${present ? " set" : " missing"}`;
    keyRow.append(chip);
  }
  const actions = document.createElement("div");
  actions.className = "models-actions";
  const refresh = document.createElement("button");
  refresh.textContent = "Refresh";
  refresh.onclick = () => void runUi(() => showPanel("models"));
  const save = document.createElement("button");
  save.textContent = "Save routing";
  save.onclick = () => void runUi(async () => {
    const prefs = {
      provider: inputValue("models-provider"),
      api_preset: inputValue("models-preset"),
      openai_model: inputValue("models-openai-model"),
      ollama_model: inputValue("models-ollama-model"),
      cursor_model: inputValue("models-cursor-model"),
      cursor_router: inputValue("models-cursor-router"),
      timeout_sec: Number(inputValue("models-timeout") || 120),
      torch_device: inputValue("models-torch-device"),
    };
    await window.eurika.request("models/prefs", { approval: true, prefs });
    await showPanel("models");
  });
  actions.append(refresh, save);
  productPanel.append(title, note, form, keyRow, status, actions);
}

function stringList(value: unknown, fallback: string[]): string[] {
  return Array.isArray(value) && value.length ? value.map((item) => String(item)) : fallback;
}

function fieldSelect(
  label: string,
  id: string,
  values: string[],
  current: string,
  labels: string[] = values,
): [HTMLLabelElement, HTMLSelectElement] {
  const caption = document.createElement("label");
  caption.htmlFor = id;
  caption.textContent = label;
  const select = document.createElement("select");
  select.id = id;
  for (const [index, value] of values.entries()) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labels[index] ?? (value || "(from .env)");
    if (value === current) option.selected = true;
    select.append(option);
  }
  return [caption, select];
}

function fieldInput(
  label: string,
  id: string,
  value: string,
  type = "text",
): [HTMLLabelElement, HTMLInputElement] {
  const caption = document.createElement("label");
  caption.htmlFor = id;
  caption.textContent = label;
  const input = document.createElement("input");
  input.id = id;
  input.type = type;
  input.value = value;
  return [caption, input];
}

function inputValue(id: string): string {
  const node = document.getElementById(id);
  if (node instanceof HTMLInputElement || node instanceof HTMLSelectElement) return node.value;
  return "";
}

function renderMarket(data: Record<string, unknown>): void {
  const portfolio = (data.portfolio ?? {}) as Record<string, unknown>;
  const events = Array.isArray(data.events) ? data.events.slice(-30) : [];
  const title = document.createElement("h3");
  title.textContent = `Market · equity ${String(portfolio.equity_usdt ?? "—")} USDT`;
  productPanel.append(title);
  const summary = document.createElement("p");
  summary.textContent =
    `Open: ${Array.isArray(data.openPositions) ? data.openPositions.length : 0}; ` +
    `Shadow: ${Array.isArray(data.shadowPositions) ? data.shadowPositions.length : 0}; ` +
    `Pending: ${Array.isArray(data.pendingOrders) ? data.pendingOrders.length : 0}`;
  productPanel.append(summary);
  for (const raw of events) {
    const event = raw as Record<string, unknown>;
    const line = document.createElement("div");
    line.className = "market-event";
    line.textContent = String(event.message ?? event.reason ?? JSON.stringify(event));
    productPanel.append(line);
  }
}

required("open-workspace").onclick = () => void runUi(() => openWorkspace());
required("refresh-files").onclick = () => void runUi(refreshFiles);
required("restore-checkpoint").onclick = () => void runUi(restoreCheckpoint);
required("clear-chat").onclick = () => void runUi(clearChatHistory);
required("cancel-chat").onclick = () => void runUi(cancelChat);
required("idle-self-dev").addEventListener("change", () => {
  void runUi(async () => {
    const box = required("idle-self-dev") as HTMLInputElement;
    await window.eurika.request("idle-self-dev/prefs", { enabled: box.checked });
    syncIdleSelfDevTimer();
  });
});
bindMentionInput(required("prompt") as HTMLTextAreaElement);
required("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  hideMentionPopup();
  const input = required("prompt") as HTMLTextAreaElement;
  const message = input.value.trim();
  if (message) void runUi(() => sendChat(message));
  input.value = "";
});
required("terminal-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = required("terminal-command") as HTMLInputElement;
  const command = input.value.trim();
  if (command) void runUi(() => runTerminal(command));
  input.value = "";
});
window.eurika.onStatus((status) => {
  statusElement.textContent = status;
  if (status === "ready") clearError();
  if (status === "error") showError("Eurika backend stopped unexpectedly. See terminal output.");
});
window.eurika.onEvent((raw) => {
  const envelope = raw as {
    method?: string;
    params?: {
      event?: string;
      data?: {
        text?: string;
        callId?: string;
        tool?: string;
        arguments?: Record<string, unknown>;
        result?: { stdout?: string; stderr?: string; status?: string };
        error?: { message?: string };
      };
    };
  };
  if (envelope.method !== "agent/event") return;
  const event = envelope.params?.event;
  const data = envelope.params?.data;
  const text = data?.text;
  if (event === "message_start") {
    if (!streamMessage) streamMessage = appendMessage("assistant", "…");
  } else if ((event === "response/chunk" || event === "message_end") && text) {
    updateStream(text);
  } else if (event === "tool/started" && data?.callId && data?.tool) {
    activeToolCalls.set(data.callId, { tool: data.tool, arguments: data.arguments });
    const detail = String(
      data.arguments?.path ?? data.arguments?.name ?? data.arguments?.query ?? "",
    );
    appendThinking(`${data.tool} ${detail}`.trim());
  } else if (event === "tool/completed" && data?.callId && data?.tool) {
    const started = activeToolCalls.get(data.callId);
    activeToolCalls.delete(data.callId);
    if (data.tool === "git_diff") {
      renderReadOnlyDiff("Workspace git diff", String(data.result?.stdout ?? ""));
    } else if (data.tool === "git_status") {
      const status = String(data.result?.status ?? data.result?.stdout ?? "");
      renderReadOnlyDiff("Workspace git status", status);
    } else if (started?.tool === "terminal") {
      const argv = Array.isArray(started.arguments?.argv) ? started.arguments?.argv : [];
      if (argv[0] === "git" && (argv[1] === "diff" || argv[1] === "status")) {
        renderReadOnlyDiff(`git ${argv[1]}`, String(data.result?.stdout ?? ""));
      }
    }
  } else if (event === "tool/failed" && data?.callId) {
    activeToolCalls.delete(data.callId);
    if (data.tool === "git_diff" && data.error?.message) {
      renderReadOnlyDiff("Workspace git diff", data.error.message);
    }
  }
});
window.eurika.onLog((line) => {
  terminal.writeln(line);
  if (/(backend error|handshake failed|traceback|modulenotfounderror)/i.test(line) &&
      !/\[eurika-rpc\] request \d+ failed/i.test(line)) {
    showError(line.trim());
  }
});
window.addEventListener("resize", fitTerminal);
for (const button of document.querySelectorAll<HTMLButtonElement>("#panel-nav button")) {
  button.onclick = () => void runUi(() => showPanel(button.dataset.panel ?? "chat"));
}
const startupWorkspace = window.eurika.startupWorkspace;
if (startupWorkspace) {
  void runUi(() => openWorkspace(startupWorkspace));
}

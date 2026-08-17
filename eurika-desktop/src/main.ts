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
  text: string;
  pendingToolCalls?: PendingCall[];
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
let chatRequestId: string | undefined;
let streamMessage: HTMLElement | undefined;
let fileTree: FileTreeNode[] = [];
const expandedFolders = new Set<string>();

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
  await restoreChatHistory();
  await refreshFiles();
}

async function restoreChatHistory(): Promise<void> {
  const history = await window.eurika.request<{
    messages: Array<{ role: string; content: string }>;
  }>("session/history", { limit: 80 });
  messagesElement.replaceChildren();
  for (const message of history.messages) {
    appendMessage(message.role, message.content);
  }
}

async function clearChatHistory(): Promise<void> {
  if (!window.confirm("Clear persisted chat history for this workspace?")) return;
  await window.eurika.request("session/clear");
  messagesElement.replaceChildren();
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
  const item = document.createElement("div");
  item.className = `message ${role}`;
  const label = document.createElement("strong");
  label.textContent = role === "user" ? "You" : "Eurika";
  const body = document.createElement("p");
  body.textContent = text;
  item.append(label, body);
  messagesElement.append(item);
  messagesElement.scrollTop = messagesElement.scrollHeight;
  return item;
}

function setChatBusy(busy: boolean): void {
  cancelChatButton.disabled = !busy;
  sendChatButton.disabled = busy;
}

function updateStream(text: string): void {
  const body = streamMessage?.querySelector("p");
  if (body) body.textContent = text;
  messagesElement.scrollTop = messagesElement.scrollHeight;
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
  const requestId = `chat-${Date.now()}`;
  chatRequestId = requestId;
  setChatBusy(true);
  try {
    const result = await window.eurika.request<ChatResult>("session/chat", {
      message,
      context: { activeFile: activePath },
    }, requestId);
    updateStream(result.text);
    await renderChatResult(result, { skipText: true });
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    updateStream(text);
    if (!/cancel/i.test(text)) throw error;
  } finally {
    if (chatRequestId === requestId) chatRequestId = undefined;
    streamMessage = undefined;
    setChatBusy(false);
  }
}

async function cancelChat(): Promise<void> {
  if (!chatRequestId) return;
  await window.eurika.cancel(chatRequestId);
}

async function renderChatResult(result: ChatResult, options: { skipText?: boolean } = {}): Promise<void> {
  if (!options.skipText) appendMessage("assistant", result.text);
  const edit = result.pendingToolCalls?.find((call) => call.proposal);
  if (edit?.proposal) renderProposal(await hydrateProposal(edit.proposal), edit);
  for (const call of result.pendingToolCalls ?? []) {
    if (call.tool !== "edit") {
      renderToolApproval(call);
    }
  }
}

function renderToolApproval(call: PendingCall): void {
  currentProposal = undefined;
  currentPendingCall = call;
  proposalElement.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = `Approval required: ${call.tool}`;
  const details = document.createElement("pre");
  details.textContent = JSON.stringify(call.arguments ?? {}, null, 2);
  const approve = document.createElement("button");
  approve.textContent = call.tool === "tests" ? "Run tests" : "Run approved";
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
    context: { activeFile: activePath },
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

function renderProposal(proposal: Proposal, pendingCall?: PendingCall): void {
  currentProposal = proposal;
  currentPendingCall = pendingCall;
  proposalElement.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = `Proposed changes (${proposal.files.length})`;
  proposalElement.append(heading);
  for (const file of proposal.files) {
    const row = document.createElement("button");
    row.textContent = file.path;
    row.onclick = () => {
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
    proposalElement.append(row);
  }
  const apply = document.createElement("button");
  apply.textContent = "Apply all";
  apply.onclick = () => void runUi(() => decideProposal(true));
  const reject = document.createElement("button");
  reject.textContent = "Reject all";
  reject.onclick = () => void runUi(() => decideProposal(false));
  proposalElement.append(apply, reject);
  const first = proposal.files[0];
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
  let outcome: unknown;
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
    outcome = await window.eurika.request("proposal/apply", { proposalId, approval: true });
    appendMessage("assistant", "Changes applied. A restore checkpoint was created.");
  } else {
    outcome = await window.eurika.request("proposal/reject", { proposalId });
    appendMessage("assistant", "Changes rejected.");
  }
  currentProposal = undefined;
  currentPendingCall = undefined;
  proposalElement.replaceChildren();
  await refreshFiles();
  if (activePath) await openFile(activePath);
  if (pendingCall) {
    const continuation = await window.eurika.request<ChatResult>("session/chat", {
      toolResults: [
        {
          callId: pendingCall.callId,
          tool: pendingCall.tool,
          result: { decision: apply ? "applied" : "rejected", outcome },
        },
      ],
      context: { activeFile: activePath },
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

async function showPanel(panel: string): Promise<void> {
  if (panel === "chat") {
    productPanel.hidden = true;
    messagesElement.hidden = false;
    return;
  }
  const response = await window.eurika.request<{
    panel: string;
    data?: Record<string, unknown>;
    commands?: Array<{ id: string; requiresApproval: boolean }>;
  }>("panel/state", { panel });
  messagesElement.hidden = true;
  productPanel.hidden = false;
  productPanel.replaceChildren();
  if (panel === "approvals") renderApprovals(response.data ?? {});
  if (panel === "commands") renderCommands(response.commands ?? []);
  if (panel === "market") renderMarket(response.data ?? {});
}

function renderApprovals(data: Record<string, unknown>): void {
  const operations = Array.isArray(data.operations)
    ? data.operations.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    : [];
  const title = document.createElement("h3");
  title.textContent = `Approvals (${operations.length})`;
  productPanel.append(title);
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
    const save = document.createElement("button");
    save.textContent = "Save decisions";
    save.onclick = () => void runUi(async () => {
      const result = await window.eurika.request<Record<string, unknown>>("approval/save", {
        approval: true,
        operations: decisions.map(({ index, select, operation }) => ({
          index,
          team_decision: select.value,
          approved_by: "desktop-user",
          target_file: operation.target_file,
          kind: operation.kind,
        })),
      });
      terminal.writeln(`[approvals] ${JSON.stringify(result)}`);
    });
    productPanel.append(save);
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
required("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
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
  const envelope = raw as { method?: string; params?: { event?: string; data?: { text?: string } } };
  if (envelope.method !== "agent/event") return;
  const event = envelope.params?.event;
  const text = envelope.params?.data?.text;
  if (event === "message_start") {
    if (!streamMessage) streamMessage = appendMessage("assistant", "…");
  } else if ((event === "response/chunk" || event === "message_end") && text) {
    updateStream(text);
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

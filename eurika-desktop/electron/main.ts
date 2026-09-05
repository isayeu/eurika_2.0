import { BackendProcess, JsonRpcId } from "@eurika/client";
import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import * as fs from "node:fs";
import * as path from "node:path";

const REQUEST_METHODS = new Set([
  "session/chat",
  "session/history",
  "session/clear",
  "tool/call",
  "workspace/list",
  "proposal/prepare",
  "proposal/get",
  "proposal/apply",
  "proposal/reject",
  "checkpoint/list",
  "checkpoint/restore",
  "panel/state",
  "approval/preview",
  "approval/save",
  "activity/recent",
  "command/run",
]);

let window: BrowserWindow | undefined;
let backend: BackendProcess | undefined;
let workspace: string | undefined;
let sessionId: string | undefined;
const inflight = new Map<string, AbortController>();

function trustStorePath(): string {
  return path.join(app.getPath("userData"), "trusted-workspaces.json");
}

function loadTrustedWorkspaces(): string[] {
  try {
    const parsed = JSON.parse(fs.readFileSync(trustStorePath(), "utf8")) as unknown;
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function rememberTrustedWorkspace(root: string): void {
  const trusted = loadTrustedWorkspaces();
  if (trusted.includes(root)) return;
  fs.mkdirSync(path.dirname(trustStorePath()), { recursive: true });
  fs.writeFileSync(trustStorePath(), JSON.stringify([...trusted, root], null, 2));
}

async function ensureWorkspaceTrusted(root: string): Promise<boolean> {
  const resolved = path.resolve(root);
  if (loadTrustedWorkspaces().includes(resolved)) return true;
  const parent = window;
  if (!parent || parent.isDestroyed()) return false;
  const choice = await dialog.showMessageBox(parent, {
    type: "warning",
    buttons: ["Trust folder", "Don't trust"],
    defaultId: 1,
    cancelId: 1,
    title: "Trust this workspace?",
    message: "Eurika will not start the backend or mutate files until this folder is trusted.",
    detail: resolved,
  });
  if (choice.response !== 0) return false;
  rememberTrustedWorkspace(resolved);
  return true;
}

function sendToRenderer(channel: string, value: unknown): void {
  const target = window;
  if (!target || target.isDestroyed() || target.webContents.isDestroyed()) return;
  target.webContents.send(channel, value);
}

async function stopBackend(): Promise<void> {
  for (const controller of inflight.values()) {
    controller.abort(new Error("Cancelled by user"));
  }
  inflight.clear();
  const current = backend;
  backend = undefined;
  sessionId = undefined;
  if (current) await current.stop();
}

async function startBackend(root: string): Promise<Record<string, unknown>> {
  await stopBackend();
  workspace = path.resolve(root);
  const next = new BackendProcess({
    command: process.env.EURIKA_PYTHON ?? "python3",
    args: ["-m", "eurika.agent.stdio", "--workspace", workspace],
    cwd: workspace,
    clientName: "eurika-desktop",
    clientCapabilities: {
      editorContext: true,
      terminal: true,
      notifications: true,
      approvals: true,
      desktopPanels: true,
    },
    manifest: {
      id: "desktop",
      name: "Eurika Desktop",
      version: "0.1.0",
      capabilities: {
        editorContext: true,
        terminal: true,
        notifications: true,
        approvals: true,
        panels: ["chat", "diff", "context", "approvals", "commands", "market"],
      },
    },
    log: (line) => sendToRenderer("eurika:log", line),
  });
  next.on("status", (status) => sendToRenderer("eurika:status", status));
  const capabilities = await next.start(workspace);
  next.client.on("notification", (method: string, params: unknown, id?: JsonRpcId) => {
    sendToRenderer("eurika:event", { method, params, id });
  });
  backend = next;
  const session = await next.client.request<{ sessionId: string }>("session/create", {
    metadata: { client: "eurika-desktop" },
  });
  sessionId = session.sessionId;
  return { workspace, sessionId, capabilities };
}

function registerIpc(): void {
  ipcMain.handle("eurika:initialize", async (_event, requested?: string) => {
    let root = requested;
    if (!root) {
      const parent = window;
      if (!parent || parent.isDestroyed()) return { cancelled: true };
      const selection = await dialog.showOpenDialog(parent, {
        title: "Open Eurika workspace",
        properties: ["openDirectory"],
      });
      root = selection.canceled ? undefined : selection.filePaths[0];
    }
    if (!root) return { cancelled: true };
    if (!(await ensureWorkspaceTrusted(root))) {
      return { untrusted: true, workspace: path.resolve(root) };
    }
    return startBackend(root);
  });
  ipcMain.handle(
    "eurika:request",
    async (
      _event,
      method: string,
      params: Record<string, unknown> = {},
      requestId?: string,
    ) => {
      if (!REQUEST_METHODS.has(method)) throw new Error(`Desktop RPC method is not allowed: ${method}`);
      if (!backend || !sessionId) throw new Error("Open a workspace first");
      const withSession =
        method === "session/chat" || method === "tool/call"
          ? { ...params, sessionId: params.sessionId ?? sessionId }
          : params;
      const controller = new AbortController();
      if (requestId) inflight.set(requestId, controller);
      try {
        return await backend.client.request(method, withSession, { signal: controller.signal });
      } finally {
        if (requestId) inflight.delete(requestId);
      }
    },
  );
  ipcMain.handle("eurika:cancel", async (_event, requestId?: string) => {
    if (requestId) {
      inflight.get(requestId)?.abort(new Error("Cancelled by user"));
    } else {
      for (const controller of inflight.values()) {
        controller.abort(new Error("Cancelled by user"));
      }
    }
    return { cancelled: true };
  });
}

function createWindow(): void {
  window = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 980,
    minHeight: 640,
    title: "Eurika",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });
  window.on("closed", () => {
    window = undefined;
  });
  void window.loadFile(path.join(__dirname, "..", "dist", "index.html"));
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();
});
app.on("window-all-closed", () => {
  void stopBackend().finally(() => app.quit());
});

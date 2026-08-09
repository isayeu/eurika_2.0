import * as vscode from "vscode";
import { BackendManager } from "./backend";
import { ChatMessage, ChatViewProvider } from "./chatView";
import { collectEditorContext } from "./context";
import { EditManager } from "./edits";
import { JsonRpcId } from "./protocol";
import { ToolDispatcher } from "./tools";

type StoredMessage = { role: "user" | "assistant"; text: string };
type SessionState = { id?: string; model?: string; messages: StoredMessage[] };
type AgentEvent = {
  type?: string;
  event?: string;
  text?: string;
  delta?: string;
  sessionId?: string;
  call?: { id: string | number; name: string; arguments?: Record<string, unknown> };
  id?: string | number;
  name?: string;
  arguments?: Record<string, unknown>;
  message?: string;
  data?: AgentEvent;
};
type PendingToolCall = {
  callId: string | number;
  tool: string;
  arguments?: Record<string, unknown>;
};
type PendingContinuation = {
  call: PendingToolCall;
  applied: string[];
  rejected: string[];
};

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const output = vscode.window.createOutputChannel("Eurika");
  const backend = new BackendManager(output);
  const edits = new EditManager(context.workspaceState);
  const tools = new ToolDispatcher(edits, output);
  let session = context.workspaceState.get<SessionState>("session", { messages: [] });
  let currentAbort: AbortController | undefined;
  let streamText = "";
  let streamCompleted = false;
  const pendingContinuations = new Map<string, PendingContinuation>();

  const view = new ChatViewProvider(context.extensionUri, () => session);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 20);
  status.name = "Eurika backend";
  status.command = "eurika.restartBackend";
  status.show();
  context.subscriptions.push(output, backend, edits, view, status);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("eurika.chat", view, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
  );

  const persist = async (): Promise<void> => {
    await context.workspaceState.update("session", session);
  };

  const updateStatus = (value: string): void => {
    status.text = `$(sparkle) Eurika: ${value}`;
    status.tooltip = value === "ready" ? "Eurika local backend is ready" : `Eurika backend: ${value}`;
    view.post("status", { status: value });
  };
  context.subscriptions.push(backend.onStatus(updateStatus));
  updateStatus(vscode.workspace.isTrusted ? "stopped" : "untrusted");

  const attachProtocol = (): void => {
    backend.client.on(
      "notification",
      (method: string, params: unknown, requestId?: JsonRpcId) => {
        if (method === "event" || method === "session/event" || method === "agent/event") {
          const envelope = params as AgentEvent;
          void handleEvent({
            ...(envelope.data ?? {}),
            event: envelope.event,
            sessionId: envelope.sessionId,
          });
        } else if (method === "tool/call") {
          void handleTool(params as AgentEvent, requestId);
        } else if (method === "capabilities") {
          const models = (params as { models?: unknown[] })?.models ?? [];
          view.post("models", { models, selected: session.model });
        }
      },
    );
  };

  const start = async (): Promise<void> => {
    if (!vscode.workspace.isTrusted) {
      updateStatus("untrusted");
      return;
    }
    try {
      const capabilities = await backend.start();
      attachProtocol();
      view.post("models", { models: capabilities.models ?? [], selected: session.model });
    } catch (error) {
      view.post("error", { message: `Backend failed to start: ${errorMessage(error)}` });
    }
  };

  const handleTool = async (event: AgentEvent, requestId?: JsonRpcId): Promise<unknown> => {
    const call = event.call ?? (event.id !== undefined && event.name
      ? { id: event.id, name: event.name, arguments: event.arguments }
      : undefined);
    if (!call) return undefined;
    try {
      const result = await tools.dispatch(call);
      if (
        result &&
        typeof result === "object" &&
        "transactionId" in result &&
        "files" in result
      ) {
        const proposal = result as { transactionId: string; files: string[] };
        view.post("proposal", proposal);
        pendingContinuations.set(proposal.transactionId, {
          call: {
            callId: call.id,
            tool: call.name,
            arguments: call.arguments,
          },
          applied: [],
          rejected: [],
        });
      }
      if (requestId !== undefined) backend.client.respond(requestId, result);
      return result;
    } catch (error) {
      const message = errorMessage(error);
      if (requestId !== undefined) {
        backend.client.respond(requestId, undefined, { code: -32001, message });
      } else {
        return { error: { message } };
      }
    }
  };

  const executeApprovedBackendTool = async (call: PendingToolCall): Promise<unknown> => {
    if (
      call.tool === "terminal" &&
      !vscode.workspace.getConfiguration("eurika").get("tools.allowTerminal", false)
    ) {
      return { status: "rejected", reason: "terminal tools are disabled in settings" };
    }
    const label = call.tool === "tests"
      ? "run workspace tests"
      : `run ${JSON.stringify(call.arguments?.argv ?? [])}`;
    const choice = await vscode.window.showWarningMessage(
      `Eurika wants to ${label}.`,
      { modal: true },
      "Run",
    );
    if (choice !== "Run") return { status: "rejected" };
    const response = await backend.client.request<{ result?: Record<string, unknown> }>(
      "tool/call",
      {
        sessionId: session.id,
        callId: call.callId,
        tool: call.tool,
        arguments: { ...(call.arguments ?? {}), approval: true },
      },
      currentAbort ? { signal: currentAbort.signal } : {},
    );
    const result: Record<string, unknown> =
      response?.result ?? (response as unknown as Record<string, unknown>);
    output.appendLine(`[${call.tool}] exit=${String(result.exitCode ?? "unknown")}`);
    output.show(true);
    return result;
  };

  const requestAgent = async (params: Record<string, unknown>): Promise<void> => {
    if (!currentAbort) throw new Error("No active chat request");
    const result = await backend.client.request<{
      sessionId?: string;
      text?: string;
      pendingToolCalls?: PendingToolCall[];
      metrics?: Record<string, unknown>;
    }>("session/chat", params, { signal: currentAbort.signal });
    if (result.metrics) output.appendLine(`[metrics] ${JSON.stringify(result.metrics)}`);
    if (result?.sessionId) session.id = result.sessionId;
    if (result?.text && !streamText && !streamCompleted) {
      streamText = result.text;
      view.post("stream", { text: result.text });
    }
    if (streamText) {
      session.messages.push({ role: "assistant", text: streamText });
      streamText = "";
      view.post("streamEnd");
    }
    const completed: Array<Record<string, unknown>> = [];
    for (const call of result?.pendingToolCalls ?? []) {
      const toolResult = call.tool === "terminal" || call.tool === "tests"
        ? await executeApprovedBackendTool(call)
        : await handleTool({
            call: {
              id: call.callId,
              name: call.tool,
              arguments: call.arguments,
            },
          });
      if (
        !toolResult ||
        typeof toolResult !== "object" ||
        !("transactionId" in toolResult)
      ) {
        completed.push({
          callId: call.callId,
          tool: call.tool,
          result: toolResult,
        });
      }
    }
    if (completed.length) {
      streamText = "";
      streamCompleted = false;
      await requestAgent({
        sessionId: session.id,
        toolResults: completed,
        context: await collectEditorContext(""),
      });
    }
  };

  const handleEvent = async (event: AgentEvent): Promise<void> => {
    const type = event.type ?? event.event;
    if (event.sessionId) session.id = event.sessionId;
    if (type === "token" || type === "delta" || type === "message_delta" || type === "response/chunk") {
      const text = event.text ?? event.delta ?? "";
      streamText += text;
      view.post("stream", { text });
    } else if (type === "message_start" || type === "start") {
      streamText = "";
      streamCompleted = false;
      view.post("streamStart");
    } else if (type === "message_end" || type === "done" || type === "complete") {
      if (streamText) session.messages.push({ role: "assistant", text: streamText });
      streamText = "";
      streamCompleted = true;
      view.post("streamEnd");
      await persist();
    } else if (type === "tool_call") {
      await handleTool(event);
    } else if (type === "tool/output") {
      if (typeof event.text === "string") output.append(event.text);
      output.show(true);
    } else if (type === "error") {
      view.post("error", { message: event.message ?? "Backend error" });
    }
  };

  const sendChat = async (text: string, model?: string): Promise<void> => {
    if (currentAbort) throw new Error("A chat request is already running");
    if (backend.currentStatus !== "ready") await start();
    if (backend.currentStatus !== "ready") return;
    session.model = model || session.model;
    session.messages.push({ role: "user", text });
    await persist();
    streamText = "";
    streamCompleted = false;
    view.post("streamStart");
    currentAbort = new AbortController();
    try {
      await requestAgent({
        sessionId: session.id,
        model: session.model,
        message: text,
        context: await collectEditorContext(text),
      });
      await persist();
    } catch (error) {
      if (!currentAbort.signal.aborted) view.post("error", { message: errorMessage(error) });
    } finally {
      currentAbort = undefined;
    }
  };

  const onViewMessage = async (message: ChatMessage): Promise<void> => {
    try {
      if (message.type === "chat") await sendChat(message.text, message.model);
      else if (message.type === "cancel") {
        currentAbort?.abort(new Error("Cancelled by user"));
      } else if (message.type === "openOutput") output.show();
      else if (message.type === "preview") await edits.preview(message.transactionId, message.file);
      else if (message.type === "apply") {
        const outcome = await edits.apply(message.transactionId, message.files);
        vscode.window.showInformationMessage("Eurika changes applied; checkpoint saved");
        const continuation = pendingContinuations.get(message.transactionId);
        if (continuation) continuation.applied.push(...outcome.applied);
        view.post("proposalUpdate", {
          transactionId: message.transactionId,
          files: outcome.remaining,
        });
        if (continuation && !outcome.remaining.length) {
          pendingContinuations.delete(message.transactionId);
          await continueAfterDecision(continuation.call, {
            status: "resolved",
            applied: continuation.applied,
            rejected: continuation.rejected,
          });
        }
      } else if (message.type === "reject") {
        const outcome = edits.reject(message.transactionId, message.files);
        const continuation = pendingContinuations.get(message.transactionId);
        if (continuation) continuation.rejected.push(...outcome.rejected);
        view.post("proposalUpdate", {
          transactionId: message.transactionId,
          files: outcome.remaining,
        });
        if (continuation && !outcome.remaining.length) {
          pendingContinuations.delete(message.transactionId);
          await continueAfterDecision(continuation.call, {
            status: "resolved",
            applied: continuation.applied,
            rejected: continuation.rejected,
          });
        }
      }
    } catch (error) {
      view.post("error", { message: errorMessage(error) });
    }
  };

  const continueAfterDecision = async (
    call: PendingToolCall,
    result: Record<string, unknown>,
  ): Promise<void> => {
    if (currentAbort) throw new Error("Wait for the current chat request to finish");
    if (backend.currentStatus !== "ready" || !session.id) return;
    currentAbort = new AbortController();
    streamText = "";
    streamCompleted = false;
    view.post("streamStart");
    try {
      await requestAgent({
        sessionId: session.id,
        toolResults: [{ callId: call.callId, tool: call.tool, result }],
        context: await collectEditorContext(""),
      });
      await persist();
    } finally {
      currentAbort = undefined;
    }
  };
  context.subscriptions.push(view.onMessage((message) => void onViewMessage(message)));

  const commandPrompt = (
    instruction: string,
    target?: { uri: vscode.Uri; range?: vscode.Range; diagnostic?: string },
  ): Promise<void> => {
    const editor = vscode.window.activeTextEditor;
    const uri = target?.uri ?? editor?.document.uri;
    const file = uri ? vscode.workspace.asRelativePath(uri, false) : "the workspace";
    const location = target?.range
      ? `\nLines: ${target.range.start.line + 1}-${target.range.end.line + 1}`
      : "";
    const diagnostic = target?.diagnostic ? `\nDiagnostic: ${target.diagnostic}` : "";
    return sendChat(`${instruction}\nTarget: @file:${JSON.stringify(file)}${location}${diagnostic}`);
  };
  context.subscriptions.push(
    vscode.commands.registerCommand("eurika.explain", () => commandPrompt("Explain the selected code clearly.")),
    vscode.commands.registerCommand(
      "eurika.fix",
      (target?: { uri: vscode.Uri; range?: vscode.Range; diagnostic?: string }) =>
        commandPrompt("Fix the selected code or relevant diagnostics. Propose edits for review.", target),
    ),
    vscode.commands.registerCommand("eurika.generateTests", () => commandPrompt("Generate focused tests for the selected code. Propose edits for review.")),
    vscode.commands.registerCommand("eurika.restartBackend", async () => {
      await backend.restart();
      attachProtocol();
      view.post("models", { models: backend.capabilities?.models ?? [], selected: session.model });
    }),
    vscode.commands.registerCommand("eurika.restoreCheckpoint", async () => {
      const result = await edits.restore();
      const suffix = result.conflicts.length ? `; skipped ${result.conflicts.length} user-modified file(s)` : "";
      vscode.window.showInformationMessage(`Restored ${result.restored.length} file(s)${suffix}`);
    }),
    vscode.workspace.onDidGrantWorkspaceTrust(() => void start()),
    vscode.languages.registerCodeActionsProvider(
      { scheme: "file" },
      {
        provideCodeActions(document, _range, actionContext) {
          return actionContext.diagnostics.map((diagnostic) => {
            const action = new vscode.CodeAction(
              `Fix with Eurika: ${diagnostic.message}`,
              vscode.CodeActionKind.QuickFix,
            );
            action.diagnostics = [diagnostic];
            action.command = {
              command: "eurika.fix",
              title: "Fix with Eurika",
              arguments: [{
                uri: document.uri,
                range: diagnostic.range,
                diagnostic: diagnostic.message,
              }],
            };
            return action;
          });
        },
      },
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] },
    ),
  );

  void start();
}

export function deactivate(): void {
  // Disposables registered by activate own backend shutdown.
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

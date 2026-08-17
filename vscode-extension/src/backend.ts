import { BackendProcess, BackendStatus, Capabilities } from "@eurika/client";
import * as vscode from "vscode";

export { BackendStatus, Capabilities };

/** VS Code adapter around the host-neutral Eurika sidecar lifecycle. */
export class BackendManager implements vscode.Disposable {
  private process?: BackendProcess;
  private readonly statusEmitter = new vscode.EventEmitter<BackendStatus>();
  readonly onStatus = this.statusEmitter.event;

  constructor(private readonly output: vscode.OutputChannel) {}

  get client() {
    if (!this.process) throw new Error("Eurika backend is not ready");
    return this.process.client;
  }

  get currentStatus(): BackendStatus {
    return this.process?.currentStatus ?? "stopped";
  }

  get capabilities(): Capabilities | undefined {
    return this.process?.capabilities;
  }

  async start(): Promise<Capabilities> {
    if (!vscode.workspace.isTrusted) throw new Error("Trust this workspace to start Eurika");
    const config = vscode.workspace.getConfiguration("eurika");
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const next = new BackendProcess({
      command: config.get<string>("backend.command", "python"),
      args: config.get<string[]>("backend.args", ["-m", "eurika.agent.stdio"]),
      cwd: config.get<string>("backend.cwd") || root,
      clientName: "eurika-vscode",
      clientCapabilities: { editorContext: true, approvals: true },
      manifest: {
        id: "vscode",
        name: "Eurika for VS Code",
        version: "0.1.0",
        capabilities: {
          editorContext: true,
          terminal: true,
          notifications: true,
          approvals: true,
          panels: ["chat"],
        },
      },
      log: (line) => this.output.appendLine(line),
    });
    next.on("status", (status: BackendStatus) => this.statusEmitter.fire(status));
    this.process = next;
    return next.start(root);
  }

  async restart(): Promise<Capabilities> {
    await this.stop();
    return this.start();
  }

  async stop(): Promise<void> {
    const process = this.process;
    this.process = undefined;
    if (process) await process.stop();
    else this.statusEmitter.fire("stopped");
  }

  dispose(): void {
    void this.stop();
    this.statusEmitter.dispose();
  }
}

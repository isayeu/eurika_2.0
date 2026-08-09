import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import * as vscode from "vscode";
import { JsonRpcClient } from "./protocol";

export type BackendStatus = "stopped" | "starting" | "ready" | "error";
export type Capabilities = {
  protocolVersion: string;
  models: Array<{ id: string; label?: string } | string>;
  tools?: string[];
  [key: string]: unknown;
};

export class BackendManager implements vscode.Disposable {
  private child?: ChildProcessWithoutNullStreams;
  private rpc?: JsonRpcClient;
  private status: BackendStatus = "stopped";
  private stopping = false;
  private readonly statusEmitter = new vscode.EventEmitter<BackendStatus>();
  readonly onStatus = this.statusEmitter.event;
  capabilities?: Capabilities;

  constructor(private readonly output: vscode.OutputChannel) {}

  get client(): JsonRpcClient {
    if (!this.rpc || this.status !== "ready") throw new Error("Eurika backend is not ready");
    return this.rpc;
  }

  get currentStatus(): BackendStatus {
    return this.status;
  }

  async start(): Promise<Capabilities> {
    if (this.status === "ready" && this.capabilities) return this.capabilities;
    if (!vscode.workspace.isTrusted) throw new Error("Trust this workspace to start Eurika");
    await this.stop();
    this.setStatus("starting");
    this.stopping = false;
    const config = vscode.workspace.getConfiguration("eurika");
    const command = config.get<string>("backend.command", "python");
    const args = config.get<string[]>("backend.args", ["-m", "eurika.agent.stdio"]);
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const cwd = config.get<string>("backend.cwd") || root;
    this.output.appendLine(`Starting backend: ${command} ${args.join(" ")}`);
    const child = spawn(command, args, {
      cwd,
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    this.child = child;
    child.stderr.on("data", (chunk) => this.output.append(chunk.toString()));
    child.on("error", (error) => {
      this.output.appendLine(`Backend error: ${error.message}`);
      this.setStatus("error");
    });
    child.on("exit", (code, signal) => {
      this.output.appendLine(`Backend exited (${code ?? signal ?? "unknown"})`);
      this.rpc?.close(new Error("Backend exited"));
      this.rpc = undefined;
      this.child = undefined;
      if (!this.stopping) this.setStatus("error");
    });
    const rpc = new JsonRpcClient(child.stdout, child.stdin, (error, line) => {
      this.output.appendLine(`${error.message}: ${line ?? ""}`);
    });
    this.rpc = rpc;
    try {
      const capabilities = await rpc.request<Capabilities>(
        "initialize",
        {
          protocolVersion: "1.0",
          client: { name: "eurika-vscode", version: "0.1.0" },
          workspace: root,
          capabilities: {
            streaming: true,
            cancellation: true,
            structuredTools: true,
            editPreview: true,
          },
        },
        { timeoutMs: 15_000 },
      );
      this.capabilities = capabilities;
      this.setStatus("ready");
      return capabilities;
    } catch (error) {
      this.output.appendLine(`Handshake failed: ${String(error)}`);
      await this.stop();
      this.setStatus("error");
      throw error;
    }
  }

  async restart(): Promise<Capabilities> {
    await this.stop();
    return this.start();
  }

  async stop(): Promise<void> {
    const child = this.child;
    if (!child) {
      this.setStatus("stopped");
      return;
    }
    this.stopping = true;
    this.rpc?.close();
    this.rpc = undefined;
    this.child = undefined;
    if (child.exitCode === null) {
      child.kill("SIGTERM");
      await new Promise<void>((resolve) => {
        const timer = setTimeout(() => {
          if (child.exitCode === null) child.kill("SIGKILL");
          resolve();
        }, 2_000);
        child.once("exit", () => {
          clearTimeout(timer);
          resolve();
        });
      });
    }
    this.setStatus("stopped");
  }

  dispose(): void {
    void this.stop();
    this.statusEmitter.dispose();
  }

  private setStatus(status: BackendStatus): void {
    this.status = status;
    this.statusEmitter.fire(status);
  }
}

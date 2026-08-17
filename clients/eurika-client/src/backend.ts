import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import { JsonRpcClient } from "./protocol";

export type BackendStatus = "stopped" | "starting" | "ready" | "error";
export type ClientManifest = {
  id: string;
  name: string;
  version: string;
  capabilities: {
    editorContext?: boolean;
    terminal?: boolean;
    notifications?: boolean;
    approvals?: boolean;
    panels?: string[];
  };
};
export type Capabilities = {
  protocolVersion: string;
  models: Array<{ id: string; label?: string } | string>;
  methods?: string[];
  tools?: Record<string, unknown> | string[];
  features?: Record<string, boolean>;
  [key: string]: unknown;
};
export type BackendOptions = {
  command: string;
  args: string[];
  cwd?: string;
  clientName: string;
  clientVersion?: string;
  clientCapabilities?: Record<string, boolean>;
  manifest?: ClientManifest;
  env?: NodeJS.ProcessEnv;
  log?: (line: string) => void;
};

/** Host-neutral lifecycle for the local Python sidecar. */
export class BackendProcess extends EventEmitter {
  private child?: ChildProcessWithoutNullStreams;
  private rpc?: JsonRpcClient;
  private status: BackendStatus = "stopped";
  private stopping = false;
  capabilities?: Capabilities;

  constructor(private readonly options: BackendOptions) {
    super();
  }

  get client(): JsonRpcClient {
    if (!this.rpc || this.status !== "ready") throw new Error("Eurika backend is not ready");
    return this.rpc;
  }

  get currentStatus(): BackendStatus {
    return this.status;
  }

  async start(workspace?: string): Promise<Capabilities> {
    if (this.status === "ready" && this.capabilities) return this.capabilities;
    await this.stop();
    this.setStatus("starting");
    this.stopping = false;
    this.log(`Starting backend: ${this.options.command} ${this.options.args.join(" ")}`);
    const child = spawn(this.options.command, this.options.args, {
      cwd: this.options.cwd || workspace,
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, ...this.options.env, PYTHONUNBUFFERED: "1" },
    });
    this.child = child;
    child.stderr.on("data", (chunk) => this.log(chunk.toString()));
    child.on("error", (error) => {
      this.log(`Backend error: ${error.message}`);
      this.setStatus("error");
    });
    child.on("exit", (code, signal) => {
      this.log(`Backend exited (${code ?? signal ?? "unknown"})`);
      this.rpc?.close(new Error("Backend exited"));
      this.rpc = undefined;
      this.child = undefined;
      if (!this.stopping) this.setStatus("error");
    });
    const rpc = new JsonRpcClient(child.stdout, child.stdin, (error, line) => {
      this.log(`${error.message}: ${line ?? ""}`);
    });
    this.rpc = rpc;
    try {
      const capabilities = await rpc.request<Capabilities>(
        "initialize",
        {
          protocolVersion: "1.0",
          client: {
            name: this.options.clientName,
            version: this.options.clientVersion ?? "0.1.0",
            manifest: this.options.manifest,
          },
          workspace,
          capabilities: {
            streaming: true,
            cancellation: true,
            structuredTools: true,
            editPreview: true,
            ...(this.options.clientCapabilities ?? {}),
          },
        },
        { timeoutMs: 15_000 },
      );
      this.capabilities = capabilities;
      this.setStatus("ready");
      return capabilities;
    } catch (error) {
      this.log(`Handshake failed: ${String(error)}`);
      await this.stop();
      this.setStatus("error");
      throw error;
    }
  }

  async restart(workspace?: string): Promise<Capabilities> {
    await this.stop();
    return this.start(workspace);
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

  private log(line: string): void {
    this.options.log?.(line);
  }

  private setStatus(status: BackendStatus): void {
    this.status = status;
    this.emit("status", status);
  }
}

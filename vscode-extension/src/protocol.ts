import { EventEmitter } from "node:events";
import { Readable, Writable } from "node:stream";
import * as readline from "node:readline";

export type JsonRpcId = number | string;
export type JsonRpcError = { code: number; message: string; data?: unknown };
export type JsonRpcMessage = {
  jsonrpc: "2.0";
  id?: JsonRpcId;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: JsonRpcError;
};

type Pending = {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  timer?: NodeJS.Timeout;
};

/** Newline-delimited JSON-RPC 2.0 transport suitable for a child process. */
export class JsonRpcClient extends EventEmitter {
  private readonly pending = new Map<JsonRpcId, Pending>();
  private readonly reader: readline.Interface;
  private nextId = 1;
  private closed = false;

  constructor(
    input: Readable,
    private readonly output: Writable,
    private readonly onProtocolError: (error: Error, line?: string) => void = () => {},
  ) {
    super();
    this.reader = readline.createInterface({ input, crlfDelay: Infinity });
    this.reader.on("line", (line) => this.receive(line));
    this.reader.on("close", () => this.close(new Error("JSON-RPC stream closed")));
  }

  request<T>(
    method: string,
    params?: unknown,
    options: { timeoutMs?: number; signal?: AbortSignal } = {},
  ): Promise<T> {
    if (this.closed) return Promise.reject(new Error("JSON-RPC client is closed"));
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      const pending: Pending = {
        resolve: resolve as (value: unknown) => void,
        reject,
      };
      if (options.timeoutMs) {
        pending.timer = setTimeout(() => {
          this.pending.delete(id);
          reject(new Error(`${method} timed out`));
        }, options.timeoutMs);
      }
      this.pending.set(id, pending);
      if (options.signal) {
        const abort = () => {
          if (this.pending.delete(id)) {
            if (pending.timer) clearTimeout(pending.timer);
            reject(options.signal?.reason ?? new Error(`${method} cancelled`));
            this.notify("$/cancelRequest", { id });
          }
        };
        if (options.signal.aborted) abort();
        else options.signal.addEventListener("abort", abort, { once: true });
      }
      if (this.pending.has(id)) this.write({ jsonrpc: "2.0", id, method, params });
    });
  }

  notify(method: string, params?: unknown): void {
    if (!this.closed) this.write({ jsonrpc: "2.0", method, params });
  }

  respond(id: JsonRpcId, result?: unknown, error?: JsonRpcError): void {
    this.write({ jsonrpc: "2.0", id, ...(error ? { error } : { result }) });
  }

  close(reason = new Error("JSON-RPC client closed")): void {
    if (this.closed) return;
    this.closed = true;
    this.reader.close();
    for (const pending of this.pending.values()) {
      if (pending.timer) clearTimeout(pending.timer);
      pending.reject(reason);
    }
    this.pending.clear();
    this.emit("closed", reason);
  }

  private write(message: JsonRpcMessage): void {
    this.output.write(`${JSON.stringify(message)}\n`);
  }

  private receive(line: string): void {
    if (!line.trim()) return;
    let message: JsonRpcMessage;
    try {
      message = JSON.parse(line) as JsonRpcMessage;
    } catch {
      this.onProtocolError(new Error("Backend emitted invalid JSON"), line);
      return;
    }
    if (message.jsonrpc !== "2.0") {
      this.onProtocolError(new Error("Backend emitted unsupported JSON-RPC version"), line);
      return;
    }
    if (message.id !== undefined && !message.method) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (pending.timer) clearTimeout(pending.timer);
      if (message.error) {
        const error = new Error(message.error.message);
        Object.assign(error, { code: message.error.code, data: message.error.data });
        pending.reject(error);
      } else {
        pending.resolve(message.result);
      }
      return;
    }
    if (message.method) {
      this.emit("notification", message.method, message.params, message.id);
      this.emit(message.method, message.params, message.id);
    }
  }
}

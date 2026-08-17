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
  abort?: () => void;
  signal?: AbortSignal;
};

/** Newline-delimited JSON-RPC 2.0 client shared by every Eurika host. */
export class JsonRpcClient {
  private readonly events = new EventEmitter();
  private readonly pending = new Map<JsonRpcId, Pending>();
  private readonly reader: readline.Interface;
  private nextId = 1;
  private closed = false;

  constructor(
    input: Readable,
    private readonly output: Writable,
    private readonly onProtocolError: (error: Error, line?: string) => void = () => {},
  ) {
    this.reader = readline.createInterface({ input, crlfDelay: Infinity });
    this.reader.on("line", (line) => this.receive(line));
    this.reader.on("close", () => this.close(new Error("JSON-RPC stream closed")));
  }

  on(eventName: string | symbol, listener: (...args: any[]) => void): this {
    this.events.on(eventName, listener);
    return this;
  }

  once(eventName: string | symbol, listener: (...args: any[]) => void): this {
    this.events.once(eventName, listener);
    return this;
  }

  request<T>(
    method: string,
    params?: unknown,
    options: { timeoutMs?: number; signal?: AbortSignal } = {},
  ): Promise<T> {
    if (this.closed) return Promise.reject(new Error("JSON-RPC client is closed"));
    const id = this.nextId++;
    return new Promise<T>((resolve, reject) => {
      const pending: Pending = { resolve: resolve as (value: unknown) => void, reject };
      if (options.timeoutMs) {
        pending.timer = setTimeout(() => {
          this.removePending(id);
          reject(new Error(`${method} timed out`));
        }, options.timeoutMs);
      }
      this.pending.set(id, pending);
      if (options.signal) {
        pending.signal = options.signal;
        pending.abort = () => {
          if (this.pending.delete(id)) {
            if (pending.timer) clearTimeout(pending.timer);
            reject(options.signal?.reason ?? new Error(`${method} cancelled`));
            this.notify("$/cancelRequest", { id });
          }
        };
        if (options.signal.aborted) pending.abort();
        else options.signal.addEventListener("abort", pending.abort, { once: true });
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
    for (const [id, pending] of this.pending) {
      this.removePending(id);
      pending.reject(reason);
    }
    this.events.emit("closed", reason);
  }

  private removePending(id: JsonRpcId): Pending | undefined {
    const pending = this.pending.get(id);
    if (!pending) return undefined;
    this.pending.delete(id);
    if (pending.timer) clearTimeout(pending.timer);
    if (pending.signal && pending.abort) pending.signal.removeEventListener("abort", pending.abort);
    return pending;
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
      const pending = this.removePending(message.id);
      if (!pending) return;
      if (message.error) {
        const detail =
          message.error.data &&
          typeof message.error.data === "object" &&
          "detail" in message.error.data &&
          typeof message.error.data.detail === "string"
            ? message.error.data.detail
            : undefined;
        const error = new Error(
          detail ? `${message.error.message}: ${detail}` : message.error.message,
        );
        Object.assign(error, { code: message.error.code, data: message.error.data });
        pending.reject(error);
      } else {
        pending.resolve(message.result);
      }
      return;
    }
    if (message.method) {
      this.events.emit("notification", message.method, message.params, message.id);
      this.events.emit(message.method, message.params, message.id);
    }
  }
}

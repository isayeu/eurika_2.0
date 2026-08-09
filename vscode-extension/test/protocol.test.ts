import assert from "node:assert/strict";
import { PassThrough } from "node:stream";
import test from "node:test";
import { JsonRpcClient } from "../src/protocol";

function transport(): {
  client: JsonRpcClient;
  backendToClient: PassThrough;
  clientToBackend: PassThrough;
} {
  const backendToClient = new PassThrough();
  const clientToBackend = new PassThrough();
  return {
    client: new JsonRpcClient(backendToClient, clientToBackend),
    backendToClient,
    clientToBackend,
  };
}

test("request writes NDJSON and resolves its response", async () => {
  const { client, backendToClient, clientToBackend } = transport();
  const requestLine = new Promise<string>((resolve) => clientToBackend.once("data", (chunk) => resolve(String(chunk))));
  const pending = client.request<{ ok: boolean }>("initialize", { version: 1 });
  const request = JSON.parse(await requestLine);
  assert.equal(request.method, "initialize");
  assert.deepEqual(request.params, { version: 1 });
  backendToClient.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: { ok: true } })}\n`);
  assert.deepEqual(await pending, { ok: true });
  client.close();
});

test("notifications are emitted by method", async () => {
  const { client, backendToClient } = transport();
  const received = new Promise<unknown>((resolve) => client.once("event", resolve));
  backendToClient.write('{"jsonrpc":"2.0","method":"event","params":{"type":"token","text":"hi"}}\n');
  assert.deepEqual(await received, { type: "token", text: "hi" });
  client.close();
});

test("aborting a request rejects and sends cancellation", async () => {
  const { client, clientToBackend } = transport();
  const lines: string[] = [];
  clientToBackend.on("data", (chunk) => lines.push(...String(chunk).trim().split("\n")));
  const controller = new AbortController();
  const pending = client.request("session/chat", {}, { signal: controller.signal });
  controller.abort(new Error("stop"));
  await assert.rejects(pending, /stop/);
  await new Promise((resolve) => setImmediate(resolve));
  const cancellation = JSON.parse(lines[1]);
  assert.equal(cancellation.method, "$/cancelRequest");
  assert.equal(cancellation.params.id, JSON.parse(lines[0]).id);
  client.close();
});

test("backend crash rejects active requests instead of hanging", async () => {
  const { client, backendToClient } = transport();
  const pending = client.request("session/chat", { message: "hello" });
  backendToClient.end();
  await assert.rejects(pending, /stream closed/);
});

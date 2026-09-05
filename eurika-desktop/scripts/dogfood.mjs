import { BackendProcess } from "@eurika/client";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repository = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const workspace = await mkdtemp(resolve(tmpdir(), "eurika-desktop-"));
await writeFile(resolve(workspace, "hello.txt"), "old\n", "utf8");
await writeFile(resolve(workspace, "alpha.txt"), "a0\n", "utf8");
await writeFile(resolve(workspace, "beta.txt"), "b0\n", "utf8");
const backend = new BackendProcess({
  command: process.env.EURIKA_PYTHON ?? "python3",
  args: ["-m", "eurika.agent.stdio", "--workspace", workspace],
  cwd: workspace,
  clientName: "eurika-desktop-dogfood",
  manifest: {
    id: "desktop-dogfood",
    name: "Eurika Desktop Dogfood",
    version: "0.1.0",
    capabilities: { editorContext: true, approvals: true, panels: ["chat", "diff"] },
  },
  env: {
    PYTHONPATH: [repository, process.env.PYTHONPATH].filter(Boolean).join(delimiter),
  },
  log: (line) => process.stderr.write(line),
});

function isApprovalError(error) {
  return Boolean(error && error.code === -32001);
}

try {
  const capabilities = await backend.start(workspace);
  if (!capabilities.features?.editProposals) throw new Error("Proposal capability missing");
  const session = await backend.client.request("session/create", {
    metadata: { client: "eurika-desktop-dogfood" },
  });
  const files = await backend.client.request("workspace/list", {});
  if (!files.files.includes("hello.txt")) throw new Error("Workspace listing failed");

  const proposal = await backend.client.request("proposal/prepare", {
    path: "hello.txt",
    oldText: "old",
    newText: "new",
  });
  await backend.client.request("proposal/apply", {
    proposalId: proposal.proposalId,
    approval: true,
  });
  if ((await readFile(resolve(workspace, "hello.txt"), "utf8")) !== "new\n") {
    throw new Error("Proposal apply failed");
  }
  await backend.client.request("checkpoint/restore", {
    checkpointId: proposal.proposalId,
    approval: true,
  });
  if ((await readFile(resolve(workspace, "hello.txt"), "utf8")) !== "old\n") {
    throw new Error("Checkpoint restore failed");
  }

  const multi = await backend.client.request("proposal/prepare", {
    edits: [
      { path: "alpha.txt", content: "A1\n" },
      { path: "beta.txt", content: "B1\n" },
    ],
  });
  const first = await backend.client.request("proposal/apply", {
    proposalId: multi.proposalId,
    paths: ["alpha.txt"],
    approval: true,
  });
  if (!first.remaining.includes("beta.txt")) {
    throw new Error("Independent apply did not leave the other file reviewable");
  }
  if ((await readFile(resolve(workspace, "alpha.txt"), "utf8")) !== "A1\n") {
    throw new Error("First-file apply failed");
  }
  if ((await readFile(resolve(workspace, "beta.txt"), "utf8")) !== "b0\n") {
    throw new Error("Unselected proposal file was mutated");
  }
  await backend.client.request("proposal/apply", {
    proposalId: multi.proposalId,
    paths: ["beta.txt"],
    approval: true,
  });
  if ((await readFile(resolve(workspace, "beta.txt"), "utf8")) !== "B1\n") {
    throw new Error("Second-file apply failed");
  }

  const conflictProposal = await backend.client.request("proposal/prepare", {
    path: "hello.txt",
    content: "agent\n",
  });
  await backend.client.request("proposal/apply", {
    proposalId: conflictProposal.proposalId,
    approval: true,
  });
  await writeFile(resolve(workspace, "hello.txt"), "user later edit\n", "utf8");
  const restore = await backend.client.request("checkpoint/restore", {
    checkpointId: conflictProposal.proposalId,
    approval: true,
  });
  if (!restore.conflicts.includes("hello.txt")) {
    throw new Error("Restore did not report a later user-edit conflict");
  }
  if (restore.restored.includes("hello.txt")) {
    throw new Error("Restore overwrote a later user edit");
  }
  if ((await readFile(resolve(workspace, "hello.txt"), "utf8")) !== "user later edit\n") {
    throw new Error("User content was lost during restore");
  }

  try {
    await backend.client.request("tool/call", {
      sessionId: session.sessionId,
      tool: "terminal",
      arguments: { argv: ["python3", "-c", "print('no')"] },
    });
    throw new Error("Terminal ran without explicit approval");
  } catch (error) {
    if (!isApprovalError(error)) throw error;
  }

  try {
    await backend.client.request("tool/call", {
      sessionId: session.sessionId,
      tool: "git_commit",
      arguments: { message: "dogfood", paths: ["hello.txt"] },
    });
    throw new Error("git_commit ran without explicit approval");
  } catch (error) {
    if (!isApprovalError(error)) throw error;
  }

  try {
    await backend.client.request("tool/call", {
      sessionId: session.sessionId,
      tool: "git_push",
      arguments: {},
    });
    throw new Error("git_push ran without explicit approval");
  } catch (error) {
    if (!isApprovalError(error)) throw error;
  }

  try {
    await backend.client.request("command/run", { command: "scan" });
    throw new Error("Command ran without explicit approval");
  } catch (error) {
    if (!isApprovalError(error)) throw error;
  }

  const market = await backend.client.request("panel/state", { panel: "market" });
  const commands = await backend.client.request("panel/state", { panel: "commands" });
  const approvals = await backend.client.request("panel/state", { panel: "approvals" });
  const context = await backend.client.request("panel/state", { panel: "context" });
  if (market.panel !== "market" || !market.data) throw new Error("Market panel did not return shared state");
  if (!commands.commands?.some((item) => item.id === "scan")) {
    throw new Error("Commands panel is missing the shared command list");
  }
  if (approvals.panel !== "approvals") throw new Error("Approvals panel did not return shared state");
  if (context.panel !== "context" || typeof context.text !== "string") {
    throw new Error("Context panel did not return shared dialog_state text");
  }

  const samplePath = resolve(workspace, "context_hitl.txt");
  const histDir = resolve(workspace, ".eurika", "chat_history");
  await mkdir(histDir, { recursive: true });
  const hitlToken = "dogfoodtoken01";
  await writeFile(
    resolve(histDir, "dialog_state.json"),
    JSON.stringify({
      pending_plan: {
        intent: "create",
        target: "context_hitl.txt",
        token: hitlToken,
        status: "pending_confirmation",
        expires_ts: 4102444800,
        entities: { content: "beta\n" },
        steps: ["create context_hitl.txt"],
        requires_confirmation: true,
        risk_level: "medium",
      },
    }),
    "utf8",
  );
  const contextPending = await backend.client.request("panel/state", { panel: "context" });
  if (!contextPending.planValid || !String(contextPending.preview?.unified_diff || "").includes("beta")) {
    throw new Error("Context panel missing dialog_state pending Diff");
  }
  const contextPreview = await backend.client.request("context/preview", {});
  if (!String(contextPreview.preview?.unified_diff || "").includes("beta")) {
    throw new Error("context/preview did not return unified diff");
  }
  try {
    await backend.client.request("context/decide", { decision: "apply", token: hitlToken });
    throw new Error("context/decide apply ran without explicit approval");
  } catch (error) {
    if (!isApprovalError(error)) throw error;
  }
  const applied = await backend.client.request("context/decide", {
    decision: "apply",
    token: hitlToken,
    approval: true,
  });
  if (!applied.ok) throw new Error(`context/decide apply failed: ${applied.error || applied.text}`);
  const afterApply = await readFile(samplePath, "utf8");
  if (afterApply !== "beta\n") throw new Error("context/decide apply did not write dialog_state create");
  const contextClear = await backend.client.request("panel/state", { panel: "context" });
  if (contextClear.planValid) throw new Error("Context still reports planValid after apply");

  await writeFile(resolve(workspace, "ok.py"), "x = 1\n", "utf8");
  const verified = await backend.client.request("proposal/prepare", {
    path: "ok.py",
    content: "x = 2\n",
  });
  await backend.client.request("proposal/apply", {
    proposalId: verified.proposalId,
    approval: true,
  });
  const diagnostics = await backend.client.request("tool/call", {
    sessionId: session.sessionId,
    tool: "diagnostics",
    arguments: { paths: ["ok.py"] },
  });
  if (!diagnostics.result || !Array.isArray(diagnostics.result.diagnostics)) {
    throw new Error("Verification did not return structured diagnostics");
  }
  if (diagnostics.result.diagnostics.length !== 0) {
    throw new Error("Clean apply reported diagnostics");
  }

  const python = process.env.EURIKA_PYTHON ?? "python3";
  const controller = new AbortController();
  const pending = backend.client.request("tool/call", {
    sessionId: session.sessionId,
    tool: "terminal",
    arguments: {
      argv: [python, "-c", "import time; time.sleep(30)"],
      approval: true,
      timeoutMs: 60_000,
    },
  }, { signal: controller.signal, timeoutMs: 15_000 });
  await new Promise((resolve) => setTimeout(resolve, 200));
  controller.abort(new Error("Cancelled by user"));
  try {
    await pending;
    throw new Error("In-flight terminal was not cancelled");
  } catch (error) {
    const text = error instanceof Error ? error.message : String(error);
    if (!/cancel/i.test(text)) throw error;
  }

  process.stdout.write("Eurika Desktop dogfood: ok\n");
} finally {
  await backend.stop();
  await rm(workspace, { recursive: true, force: true });
}

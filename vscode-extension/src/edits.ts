import * as path from "node:path";
import * as fs from "node:fs";
import * as vscode from "vscode";
import { decideRestore, sha256, SnapshotEntry } from "./pure";

export type ProposedEdit = {
  uri?: string;
  path?: string;
  newText?: string;
  range?: {
    start: { line: number; character: number };
    end: { line: number; character: number };
  };
};

type ProposedFile = {
  uri: vscode.Uri;
  before?: Uint8Array;
  after?: Uint8Array;
};

type Transaction = { id: string; files: Map<string, ProposedFile> };
type Checkpoint = { id: string; createdAt: string; entries: SnapshotEntry[] };

export class EditManager implements vscode.TextDocumentContentProvider, vscode.Disposable {
  private readonly proposals = new Map<string, Transaction>();
  private readonly changed = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this.changed.event;
  private readonly registration: vscode.Disposable;

  constructor(private readonly state: vscode.Memento) {
    this.registration = vscode.workspace.registerTextDocumentContentProvider("eurika-preview", this);
  }

  async stage(
    edits: ProposedEdit[],
    transactionId?: string,
  ): Promise<{ transactionId: string; files: string[] }> {
    if (!vscode.workspace.isTrusted) throw new Error("Workspace trust is required for edits");
    const id = transactionId ?? `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const files = new Map<string, ProposedFile>();
    for (const edit of edits) {
      const uri = resolveWorkspaceUri(edit.uri ?? edit.path ?? "");
      const key = uri.toString();
      let file = files.get(key);
      if (!file) {
        const before = await readOptional(uri);
        file = { uri, before, after: before };
        files.set(key, file);
      }
      if (edit.newText === undefined) {
        file.after = undefined;
      } else if (!edit.range) {
        file.after = Buffer.from(edit.newText);
      } else {
        const current = file.after ?? new Uint8Array();
        const document = await vscode.workspace.openTextDocument({
          content: Buffer.from(current).toString("utf8"),
        });
        const range = new vscode.Range(
          edit.range.start.line,
          edit.range.start.character,
          edit.range.end.line,
          edit.range.end.character,
        );
        const text = document.getText();
        file.after = Buffer.from(
          text.slice(0, document.offsetAt(range.start)) +
            edit.newText +
            text.slice(document.offsetAt(range.end)),
        );
      }
    }
    this.proposals.set(id, { id, files });
    return { transactionId: id, files: [...files.keys()] };
  }

  async preview(transactionId: string, uriText?: string): Promise<void> {
    const transaction = this.requireTransaction(transactionId);
    const file = uriText ? transaction.files.get(uriText) : transaction.files.values().next().value;
    if (!file) throw new Error("No proposed file to preview");
    const relative = vscode.workspace.asRelativePath(file.uri, false);
    const left = file.before === undefined
      ? vscode.Uri.parse(`untitled:Eurika new file ${relative}`)
      : file.uri;
    const right = vscode.Uri.parse(
      `eurika-preview:/${encodeURIComponent(transactionId)}/${encodeURIComponent(file.uri.toString())}`,
    );
    await vscode.commands.executeCommand("vscode.diff", left, right, `Eurika Preview: ${relative}`);
  }

  async apply(
    transactionId: string,
    selectedUris?: string[],
  ): Promise<{ checkpointId: string; applied: string[]; remaining: string[] }> {
    if (!vscode.workspace.isTrusted) throw new Error("Workspace trust is required for edits");
    const transaction = this.requireTransaction(transactionId);
    const selected = new Set(selectedUris ?? transaction.files.keys());
    const edit = new vscode.WorkspaceEdit();
    const entries: SnapshotEntry[] = [];
    for (const [key, file] of transaction.files) {
      if (!selected.has(key)) continue;
      const current = await readOptional(file.uri);
      const currentHash = current && sha256(current);
      const stagedHash = file.before && sha256(file.before);
      if (currentHash !== stagedHash) {
        throw new Error(`File changed after preview: ${vscode.workspace.asRelativePath(file.uri, false)}`);
      }
      if (file.after === undefined) {
        edit.deleteFile(file.uri, { ignoreIfNotExists: true });
      } else {
        edit.createFile(file.uri, { ignoreIfExists: true });
        edit.replace(file.uri, fullRange(file.before), Buffer.from(file.after).toString("utf8"));
      }
      entries.push({
        uri: key,
        beforeHash: file.before && sha256(file.before),
        beforeBase64: file.before && Buffer.from(file.before).toString("base64"),
        appliedHash: file.after && sha256(file.after),
      });
    }
    if (!entries.length) throw new Error("Select at least one file to apply");
    const checkpoint: Checkpoint = {
      id: transactionId,
      createdAt: new Date().toISOString(),
      entries,
    };
    const previousCheckpoints = this.state.get<Checkpoint[]>("checkpoints", []).map((item) => ({
      ...item,
      entries: item.entries.map((entry) => ({ ...entry })),
    }));
    await this.saveCheckpoint(checkpoint);
    let applied = false;
    try {
      applied = await vscode.workspace.applyEdit(edit);
    } catch (error) {
      await this.state.update("checkpoints", previousCheckpoints);
      throw error;
    }
    if (!applied) {
      await this.state.update("checkpoints", previousCheckpoints);
      throw new Error("VS Code rejected the workspace edit");
    }
    for (const uri of selected) transaction.files.delete(uri);
    if (!transaction.files.size) this.proposals.delete(transactionId);
    return {
      checkpointId: checkpoint.id,
      applied: entries.map((entry) => entry.uri),
      remaining: [...transaction.files.keys()],
    };
  }

  reject(
    transactionId: string,
    selectedUris?: string[],
  ): { rejected: string[]; remaining: string[] } {
    const transaction = this.requireTransaction(transactionId);
    if (!selectedUris) {
      const rejected = [...transaction.files.keys()];
      this.proposals.delete(transactionId);
      return { rejected, remaining: [] };
    }
    const rejected = selectedUris.filter((uri) => transaction.files.has(uri));
    for (const uri of selectedUris) transaction.files.delete(uri);
    if (!transaction.files.size) this.proposals.delete(transactionId);
    return { rejected, remaining: [...transaction.files.keys()] };
  }

  async restore(checkpointId?: string): Promise<{ restored: string[]; conflicts: string[] }> {
    const checkpoints = this.state.get<Checkpoint[]>("checkpoints", []);
    const checkpoint = checkpointId
      ? checkpoints.find((item) => item.id === checkpointId)
      : checkpoints.at(-1);
    if (!checkpoint) throw new Error("No Eurika checkpoint is available");
    const edit = new vscode.WorkspaceEdit();
    const restored: string[] = [];
    const conflicts: string[] = [];
    for (const entry of checkpoint.entries) {
      const uri = vscode.Uri.parse(entry.uri);
      const current = await readOptional(uri);
      const decision = decideRestore(entry, current);
      if (decision.action === "conflict") {
        conflicts.push(entry.uri);
      } else if (decision.action === "delete") {
        edit.deleteFile(uri, { ignoreIfNotExists: true });
        restored.push(entry.uri);
      } else {
        edit.createFile(uri, { ignoreIfExists: true });
        edit.replace(uri, fullRange(current), Buffer.from(decision.bytes).toString("utf8"));
        restored.push(entry.uri);
      }
    }
    if (restored.length && !(await vscode.workspace.applyEdit(edit))) {
      throw new Error("VS Code rejected checkpoint restore");
    }
    const unresolved = checkpoint.entries.filter((entry) => conflicts.includes(entry.uri));
    const updated = checkpoints.filter((item) => item !== checkpoint);
    if (unresolved.length) updated.push({ ...checkpoint, entries: unresolved });
    await this.state.update("checkpoints", updated);
    return { restored, conflicts };
  }

  provideTextDocumentContent(uri: vscode.Uri): string {
    const [encodedTransaction, encodedUri] = uri.path.slice(1).split("/");
    const transaction = this.proposals.get(decodeURIComponent(encodedTransaction));
    const file = transaction?.files.get(decodeURIComponent(encodedUri ?? ""));
    return file?.after === undefined ? "" : Buffer.from(file.after).toString("utf8");
  }

  dispose(): void {
    this.registration.dispose();
    this.changed.dispose();
  }

  private requireTransaction(id: string): Transaction {
    const transaction = this.proposals.get(id);
    if (!transaction) throw new Error(`Unknown edit transaction: ${id}`);
    return transaction;
  }

  private async saveCheckpoint(checkpoint: Checkpoint): Promise<void> {
    const checkpoints = this.state.get<Checkpoint[]>("checkpoints", []);
    const existing = checkpoints.find((item) => item.id === checkpoint.id);
    if (existing) {
      const merged = new Map(existing.entries.map((entry) => [entry.uri, entry]));
      for (const entry of checkpoint.entries) {
        if (!merged.has(entry.uri)) merged.set(entry.uri, entry);
      }
      existing.entries = [...merged.values()];
    } else {
      checkpoints.push(checkpoint);
    }
    await this.state.update("checkpoints", checkpoints.slice(-20));
  }
}

function resolveWorkspaceUri(value: string): vscode.Uri {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri;
  if (!root) throw new Error("Open a workspace before applying edits");
  const uri = value.startsWith("file:")
    ? vscode.Uri.parse(value)
    : vscode.Uri.joinPath(root, value.replace(/^[/\\]+/, ""));
  const relative = path.relative(root.fsPath, uri.fsPath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Edits outside the workspace are not allowed");
  }
  if (root.scheme === "file" && uri.scheme === "file") {
    const rootReal = fs.realpathSync(root.fsPath);
    let ancestor = uri.fsPath;
    const suffix: string[] = [];
    while (!fs.existsSync(ancestor)) {
      const parent = path.dirname(ancestor);
      if (parent === ancestor) break;
      suffix.unshift(path.basename(ancestor));
      ancestor = parent;
    }
    const resolvedAncestor = fs.realpathSync(ancestor);
    const resolvedTarget = path.resolve(resolvedAncestor, ...suffix);
    const realRelative = path.relative(rootReal, resolvedTarget);
    if (realRelative.startsWith("..") || path.isAbsolute(realRelative)) {
      throw new Error("Edits through symlinks outside the workspace are not allowed");
    }
  }
  return uri;
}

async function readOptional(uri: vscode.Uri): Promise<Uint8Array | undefined> {
  const open = vscode.workspace.textDocuments.find(
    (document) => document.uri.toString() === uri.toString(),
  );
  if (open) return Buffer.from(open.getText());
  try {
    return await vscode.workspace.fs.readFile(uri);
  } catch {
    return undefined;
  }
}

function fullRange(content?: Uint8Array): vscode.Range {
  const text = content ? Buffer.from(content).toString("utf8") : "";
  const lines = text.split(/\r?\n/);
  return new vscode.Range(0, 0, Math.max(0, lines.length - 1), lines.at(-1)?.length ?? 0);
}

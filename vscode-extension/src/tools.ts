import * as path from "node:path";
import * as fs from "node:fs";
import * as vscode from "vscode";
import { EditManager, ProposedEdit } from "./edits";
import { plainRange } from "./context";

type ToolCall = { id: string | number; name: string; arguments?: Record<string, unknown> };

export class ToolDispatcher {
  constructor(
    private readonly edits: EditManager,
    private readonly output: vscode.OutputChannel,
  ) {}

  async dispatch(call: ToolCall): Promise<unknown> {
    if (!vscode.workspace.isTrusted && ["edit", "terminal", "tests", "git_commit", "git_push"].includes(call.name)) {
      throw new Error(`Tool '${call.name}' requires workspace trust`);
    }
    const args = call.arguments ?? {};
    switch (call.name) {
      case "search":
        return searchWorkspace(String(args.query ?? ""), String(args.glob ?? "**/*"), Number(args.limit ?? 100));
      case "read":
        return readFile(String(args.uri ?? args.path ?? ""), Number(args.startLine ?? 0), args.endLine as number | undefined);
      case "edit": {
        let requested: ProposedEdit[];
        if (Array.isArray(args.edits)) {
          requested = [];
          const seen = new Set<string>();
          for (const value of args.edits as Array<Record<string, unknown>>) {
            const target = String(value.uri ?? value.path ?? "");
            const key = workspaceUri(target).toString();
            if (seen.has(key)) throw new Error(`Batch edit contains duplicate file: ${target}`);
            seen.add(key);
            if (typeof value.oldText === "string" && typeof value.newText === "string") {
              requested.push(await replacementEdit(target, value.oldText, value.newText));
            } else {
              const replacement = typeof value.content === "string"
                ? value.content
                : typeof value.newText === "string"
                  ? value.newText
                  : undefined;
              if (replacement === undefined && value.delete !== true) {
                throw new Error("Each edit requires content, oldText/newText, or delete=true");
              }
              requested.push({
                path: target,
                newText: replacement,
              });
            }
          }
        } else if (typeof args.oldText === "string" && typeof args.newText === "string") {
          requested = [await replacementEdit(String(args.path ?? ""), args.oldText, args.newText)];
        } else {
          if (typeof args.content !== "string" && args.delete !== true) {
            throw new Error("Edit requires content, oldText/newText, or delete=true");
          }
          requested = [{
            path: String(args.path ?? ""),
            newText: typeof args.content === "string" ? args.content : undefined,
          }];
        }
        const proposal = await this.edits.stage(requested);
        if (args.preview !== false) await this.edits.preview(proposal.transactionId);
        return { ...proposal, status: "awaiting_user_approval" };
      }
      case "diagnostics":
        return getDiagnostics(args.uri ? String(args.uri) : undefined);
      case "git_diff":
        return gitDiff(Boolean(args.staged));
      case "terminal":
        return this.runTerminal(
          typeof args.command === "string"
            ? args.command
            : Array.isArray(args.argv)
              ? args.argv.map((part) => shellQuote(String(part))).join(" ")
              : "",
          String(args.name ?? "Eurika"),
        );
      case "tests":
        return this.runTests();
      default:
        throw new Error(`Unsupported tool: ${call.name}`);
    }
  }

  private async runTerminal(command: string, name: string): Promise<object> {
    if (!command.trim()) throw new Error("Terminal command cannot be empty");
    if (!vscode.workspace.getConfiguration("eurika").get("tools.allowTerminal", false)) {
      throw new Error("Terminal tools are disabled in Eurika settings");
    }
    const choice = await vscode.window.showWarningMessage(
      `Eurika wants to run: ${command}`,
      { modal: true },
      "Run",
    );
    if (choice !== "Run") return { launched: false, reason: "rejected" };
    const terminal = vscode.window.createTerminal({ name, cwd: vscode.workspace.workspaceFolders?.[0]?.uri });
    terminal.show();
    terminal.sendText(command, true);
    this.output.appendLine(`Terminal launched: ${command}`);
    return { launched: true, note: "Output remains in the VS Code terminal" };
  }

  private async runTests(): Promise<object> {
    const choice = await vscode.window.showWarningMessage(
      "Eurika wants to run workspace tests.",
      { modal: true },
      "Run Tests",
    );
    if (choice !== "Run Tests") return { launched: false, reason: "rejected" };
    await vscode.commands.executeCommand("testing.runAll");
    return { launched: true, note: "Results are available in the Test Results panel" };
  }
}

async function searchWorkspace(query: string, glob: string, limit: number): Promise<object[]> {
  if (!query) throw new Error("Search query cannot be empty");
  const files = await vscode.workspace.findFiles(
    glob,
    "**/{.git,node_modules,.venv,venv,dist,out,__pycache__}/**",
    Math.min(2_000, limit * 20),
  );
  let pattern: RegExp;
  try {
    pattern = new RegExp(query, "i");
  } catch {
    pattern = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
  }
  const results: object[] = [];
  for (const uri of files) {
    if (results.length >= limit) break;
    let text: string;
    try {
      text = Buffer.from(await vscode.workspace.fs.readFile(uri)).toString("utf8");
    } catch {
      continue;
    }
    for (const [index, line] of text.split(/\r?\n/).entries()) {
      if (pattern.test(line)) {
        results.push({ uri: uri.toString(), line: index, text: line.slice(0, 500) });
        if (results.length >= limit) break;
      }
      pattern.lastIndex = 0;
    }
  }
  return results;
}

async function readFile(value: string, startLine: number, endLine?: number): Promise<object> {
  const uri = workspaceUri(value);
  const document = await vscode.workspace.openTextDocument(uri);
  const lines = document.getText().split(/\r?\n/);
  const start = Math.max(0, startLine);
  const end = Math.min(lines.length, endLine ?? lines.length);
  return { uri: uri.toString(), startLine: start, endLine: end, text: lines.slice(start, end).join("\n") };
}

function getDiagnostics(value?: string): object[] {
  const groups = value ? [[workspaceUri(value), vscode.languages.getDiagnostics(workspaceUri(value))] as const] : vscode.languages.getDiagnostics();
  return groups.flatMap(([uri, diagnostics]) =>
    diagnostics.map((diagnostic) => ({
      uri: uri.toString(),
      severity: vscode.DiagnosticSeverity[diagnostic.severity],
      message: diagnostic.message,
      source: diagnostic.source,
      code: diagnostic.code,
      range: plainRange(diagnostic.range),
    })),
  );
}

async function gitDiff(staged: boolean): Promise<string> {
  const extension = vscode.extensions.getExtension("vscode.git");
  const git = extension?.isActive ? extension.exports : await extension?.activate();
  const repo = git?.getAPI?.(1)?.repositories?.[0];
  if (!repo) throw new Error("No Git repository is available");
  return repo.diff(staged);
}

function workspaceUri(value: string): vscode.Uri {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri;
  if (!root) throw new Error("Open a workspace first");
  const uri = value.startsWith("file:")
    ? vscode.Uri.parse(value)
    : vscode.Uri.joinPath(root, value.replace(/^[/\\]+/, ""));
  const relative = path.relative(root.fsPath, uri.fsPath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Paths outside the workspace are not allowed");
  }
  if (root.scheme === "file" && uri.scheme === "file") {
    const rootReal = fs.realpathSync(root.fsPath);
    const targetReal = realPathForCandidate(uri.fsPath);
    const realRelative = path.relative(rootReal, targetReal);
    if (realRelative.startsWith("..") || path.isAbsolute(realRelative)) {
      throw new Error("Paths through symlinks outside the workspace are not allowed");
    }
  }
  return uri;
}

function shellQuote(value: string): string {
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(value)) return value;
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function realPathForCandidate(candidate: string): string {
  let ancestor = candidate;
  const suffix: string[] = [];
  while (!fs.existsSync(ancestor)) {
    const parent = path.dirname(ancestor);
    if (parent === ancestor) break;
    suffix.unshift(path.basename(ancestor));
    ancestor = parent;
  }
  return path.resolve(fs.realpathSync(ancestor), ...suffix);
}

async function replacementEdit(
  targetValue: string,
  oldText: string,
  newText: string,
): Promise<ProposedEdit> {
  if (!oldText) throw new Error("oldText cannot be empty");
  const target = workspaceUri(targetValue);
  const current = (await vscode.workspace.openTextDocument(target)).getText();
  const occurrences = current.split(oldText).length - 1;
  if (occurrences !== 1) {
    throw new Error(`oldText must occur exactly once; found ${occurrences}`);
  }
  return {
    uri: target.toString(),
    newText: current.replace(oldText, newText),
  };
}

import * as path from "node:path";
import * as fs from "node:fs";
import * as vscode from "vscode";
import { matchesGlob, parseMentions, parseRule, RuleDocument } from "./pure";

export type EditorContext = {
  selection?: { uri: string; range: unknown; text: string };
  activeFile?: { uri: string; language: string; text: string };
  openFiles: Array<{ uri: string; language: string; text: string }>;
  diagnostics: Array<{ uri: string; severity: string; message: string; range: unknown }>;
  gitDiff?: string;
  mentions: Array<{ uri: string; text: string }>;
  rules: RuleDocument[];
  truncated: boolean;
};

const EXCLUDE = "**/{.git,node_modules,.venv,venv,dist,out,__pycache__}/**";

export async function collectEditorContext(prompt: string): Promise<EditorContext> {
  const maxBytes = vscode.workspace.getConfiguration("eurika").get("context.maxBytes", 200_000);
  let remaining = maxBytes;
  let truncated = false;
  const consume = (text: string, sourceLimit = Number.POSITIVE_INFINITY): string => {
    const bytes = Buffer.from(text);
    const allowed = Math.max(0, Math.min(bytes.length, remaining, sourceLimit));
    if (allowed < bytes.length) truncated = true;
    const part = bytes.subarray(0, allowed).toString("utf8");
    remaining -= allowed;
    return part;
  };

  const candidateEditor = vscode.window.activeTextEditor;
  const editor = candidateEditor && vscode.workspace.getWorkspaceFolder(candidateEditor.document.uri)
    ? candidateEditor
    : undefined;
  const selection =
    editor && !editor.selection.isEmpty
      ? {
          uri: editor.document.uri.toString(),
          range: plainRange(editor.selection),
          text: consume(editor.document.getText(editor.selection), 50_000),
        }
      : undefined;

  const activeRelative = editor ? vscode.workspace.asRelativePath(editor.document.uri, false) : "";
  const rules = (await loadRules()).filter(
    (rule) => rule.alwaysApply || !rule.globs.length || rule.globs.some((glob) => matchesGlob(activeRelative, glob)),
  ).map((rule) => ({ ...rule, content: consume(rule.content, 30_000) }));

  const mentions: Array<{ uri: string; text: string }> = [];
  for (const mention of parseMentions(prompt)) {
    for (const uri of await resolveMention(mention.kind, mention.path)) {
      if (!remaining) break;
      try {
        const open = vscode.workspace.textDocuments.find(
          (document) => document.uri.toString() === uri.toString(),
        );
        const text = open
          ? open.getText()
          : Buffer.from(await vscode.workspace.fs.readFile(uri)).toString("utf8");
        mentions.push({
          uri: uri.toString(),
          text: consume(text, 80_000),
        });
      } catch {
        // Missing, binary, and inaccessible mentions are omitted.
      }
    }
  }

  const activeFile = editor
    ? {
        uri: editor.document.uri.toString(),
        language: editor.document.languageId,
        text: consume(editor.document.getText(), 80_000),
      }
    : undefined;
  const openFiles = vscode.workspace.textDocuments
    .filter(
      (doc) =>
        doc.uri.scheme === "file" &&
        doc !== editor?.document &&
        vscode.workspace.getWorkspaceFolder(doc.uri) !== undefined,
    )
    .map((doc) => ({
      uri: doc.uri.toString(),
      language: doc.languageId,
      text: consume(doc.getText(), 30_000),
    }))
    .filter((doc) => doc.text.length > 0);
  const diagnostics = vscode.languages.getDiagnostics().flatMap(([uri, items]) =>
    vscode.workspace.getWorkspaceFolder(uri) ? items.map((item) => ({
      uri: uri.toString(),
      severity: vscode.DiagnosticSeverity[item.severity],
      message: consume(item.message, 2_000),
      range: plainRange(item.range),
    })).filter((item) => item.message.length > 0) : [],
  );
  return {
    selection,
    activeFile,
    openFiles,
    diagnostics,
    gitDiff: consume(await getGitDiff(), 50_000),
    mentions,
    rules,
    truncated,
  };
}

async function resolveMention(kind: "file" | "folder", value: string): Promise<vscode.Uri[]> {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri;
  if (!root) return [];
  const candidate = vscode.Uri.joinPath(root, value.replace(/^[/\\]+/, ""));
  const relative = path.relative(root.fsPath, candidate.fsPath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return [];
  if (root.scheme === "file" && candidate.scheme === "file") {
    const rootReal = fs.realpathSync(root.fsPath);
    const candidateReal = realPathForCandidate(candidate.fsPath);
    const realRelative = path.relative(rootReal, candidateReal);
    if (realRelative.startsWith("..") || path.isAbsolute(realRelative)) return [];
  }
  if (kind === "file") return [candidate];
  return vscode.workspace.findFiles(new vscode.RelativePattern(candidate, "**/*"), EXCLUDE, 200);
}

async function loadRules(): Promise<RuleDocument[]> {
  const files = await vscode.workspace.findFiles(".eurika/rules/**/*.{md,mdc}", EXCLUDE, 100);
  return Promise.all(
    files.map(async (uri) =>
      parseRule(
        vscode.workspace.asRelativePath(uri, false),
        Buffer.from(await vscode.workspace.fs.readFile(uri)).toString("utf8"),
      ),
    ),
  );
}

async function getGitDiff(): Promise<string> {
  try {
    const extension = vscode.extensions.getExtension("vscode.git");
    const git = extension?.isActive ? extension.exports : await extension?.activate();
    const api = git?.getAPI?.(1);
    const repo = api?.repositories?.[0];
    if (!repo) return "";
    const [working, staged] = await Promise.all([repo.diff(), repo.diff(true)]);
    return `${working}\n${staged}`.trim();
  } catch {
    return "";
  }
}

export function plainRange(range: vscode.Range): object {
  return {
    start: { line: range.start.line, character: range.start.character },
    end: { line: range.end.line, character: range.end.character },
  };
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

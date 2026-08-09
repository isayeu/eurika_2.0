import { createHash } from "node:crypto";

export type Mention = { kind: "file" | "folder"; path: string };

/** Parse explicit @file:path and @folder:path references, with optional quotes. */
export function parseMentions(text: string): Mention[] {
  const mentions: Mention[] = [];
  const pattern = /@(file|folder):(?:"([^"]+)"|'([^']+)'|([^\s,;]+))/g;
  for (const match of text.matchAll(pattern)) {
    const path = (match[2] ?? match[3] ?? match[4] ?? "").trim();
    if (path && !path.includes("\0")) {
      mentions.push({ kind: match[1] as Mention["kind"], path });
    }
  }
  return mentions;
}

export type RuleDocument = {
  source: string;
  content: string;
  globs: string[];
  alwaysApply: boolean;
};

/** Parse the small frontmatter subset used by .eurika/rules markdown files. */
export function parseRule(source: string, raw: string): RuleDocument {
  let body = raw;
  let globs: string[] = [];
  let alwaysApply = false;
  const frontmatter = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/;
  const match = raw.match(frontmatter);
  if (match) {
    body = raw.slice(match[0].length);
    for (const line of match[1].split(/\r?\n/)) {
      const separator = line.indexOf(":");
      if (separator < 0) continue;
      const key = line.slice(0, separator).trim();
      const value = line.slice(separator + 1).trim();
      if (key === "alwaysApply") alwaysApply = value === "true";
      if (key === "glob" || key === "globs") {
        globs = value
          .replace(/^\[|\]$/g, "")
          .split(",")
          .map((item) => item.trim().replace(/^['"]|['"]$/g, ""))
          .filter(Boolean);
      }
    }
  }
  return { source, content: body.trim(), globs, alwaysApply };
}

export function sha256(content: Uint8Array | string): string {
  return createHash("sha256").update(content).digest("hex");
}

export type SnapshotEntry = {
  uri: string;
  beforeHash?: string;
  beforeBase64?: string;
  appliedHash?: string;
};

export type RestoreDecision =
  | { action: "restore"; bytes: Uint8Array }
  | { action: "delete" }
  | { action: "conflict"; reason: string };

/** Restore only when the current file still equals the content we applied. */
export function decideRestore(
  entry: SnapshotEntry,
  current: Uint8Array | undefined,
): RestoreDecision {
  const currentHash = current === undefined ? undefined : sha256(current);
  if (currentHash !== entry.appliedHash) {
    return { action: "conflict", reason: "File changed after checkpoint apply" };
  }
  if (entry.beforeBase64 === undefined) return { action: "delete" };
  return {
    action: "restore",
    bytes: Buffer.from(entry.beforeBase64, "base64"),
  };
}

export function matchesGlob(path: string, glob: string): boolean {
  const escaped = glob
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*\//g, "\0")
    .replace(/\*\*/g, "\u0001")
    .replace(/\*/g, "[^/]*")
    .replace(/\?/g, "[^/]")
    .replace(/\0/g, "(?:.*/)?")
    .replace(/\u0001/g, ".*");
  return new RegExp(`^${escaped}$`).test(path);
}

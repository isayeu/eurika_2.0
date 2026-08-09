import assert from "node:assert/strict";
import test from "node:test";
import {
  decideRestore,
  matchesGlob,
  parseMentions,
  parseRule,
  sha256,
  SnapshotEntry,
} from "../src/pure";

test("parses quoted file and folder mentions", () => {
  assert.deepEqual(parseMentions('check @file:"src/hello world.ts", then @folder:tests/unit'), [
    { kind: "file", path: "src/hello world.ts" },
    { kind: "folder", path: "tests/unit" },
  ]);
});

test("parses scoped rule frontmatter", () => {
  assert.deepEqual(
    parseRule(".eurika/rules/typescript.mdc", "---\nglobs: [src/**/*.ts, test/*.ts]\nalwaysApply: false\n---\nUse strict types."),
    {
      source: ".eurika/rules/typescript.mdc",
      content: "Use strict types.",
      globs: ["src/**/*.ts", "test/*.ts"],
      alwaysApply: false,
    },
  );
  assert.equal(matchesGlob("src/lib/file.ts", "src/**/*.ts"), true);
  assert.equal(matchesGlob("src/file.ts", "src/**/*.ts"), true);
  assert.equal(matchesGlob("README.md", "src/**/*.ts"), false);
});

test("checkpoint restore rejects files modified after apply", () => {
  const before = Buffer.from("before");
  const applied = Buffer.from("applied");
  const entry: SnapshotEntry = {
    uri: "file:///work/a.txt",
    beforeHash: sha256(before),
    beforeBase64: before.toString("base64"),
    appliedHash: sha256(applied),
  };
  const restore = decideRestore(entry, applied);
  assert.equal(restore.action, "restore");
  if (restore.action === "restore") assert.equal(Buffer.from(restore.bytes).toString(), "before");
  assert.equal(decideRestore(entry, Buffer.from("user change")).action, "conflict");
});

test("checkpoint restore removes a newly created unchanged file", () => {
  const applied = Buffer.from("new");
  assert.deepEqual(
    decideRestore({ uri: "file:///work/new.txt", appliedHash: sha256(applied) }, applied),
    { action: "delete" },
  );
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { ancestorFolders, buildFileTree } from "../src/file-tree.ts";

test("buildFileTree nests folders and sorts folders before files", () => {
  const tree = buildFileTree([
    "z.txt",
    "src/b.ts",
    "src/a.ts",
    "docs/guide.md",
  ]);
  assert.equal(tree.map((node) => node.name).join(","), "docs,src,z.txt");
  assert.equal(tree[0].kind, "folder");
  assert.equal(tree[0].path, "docs");
  assert.equal(tree[1].children.map((node) => node.name).join(","), "a.ts,b.ts");
  assert.equal(tree[1].children[0].path, "src/a.ts");
  assert.equal(tree[1].children[0].kind, "file");
});

test("ancestorFolders lists every parent of a nested file", () => {
  assert.deepEqual(ancestorFolders("eurika/agent/stdio.py"), [
    "eurika",
    "eurika/agent",
  ]);
  assert.deepEqual(ancestorFolders("README.md"), []);
});

test("desktop renders a collapsible tree instead of a flat path dump", async () => {
  const renderer = await readFile(new URL("../src/main.ts", import.meta.url), "utf8");
  assert.match(renderer, /from "\.\/file-tree"/);
  assert.match(renderer, /expandedFolders/);
  assert.match(renderer, /renderFileTree/);
  assert.match(renderer, /tree-row folder/);
  assert.doesNotMatch(renderer, /button\.textContent = path/);
});

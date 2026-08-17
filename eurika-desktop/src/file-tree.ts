export type FileTreeNode = {
  name: string;
  path: string;
  kind: "file" | "folder";
  children: FileTreeNode[];
};

export function buildFileTree(paths: string[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];
  const folders = new Map<string, FileTreeNode>();
  for (const filePath of paths) {
    const parts = filePath.split("/").filter(Boolean);
    if (parts.length === 0) continue;
    let parent = root;
    let prefix = "";
    for (let index = 0; index < parts.length; index += 1) {
      const name = parts[index];
      const current = prefix ? `${prefix}/${name}` : name;
      const isFile = index === parts.length - 1;
      if (isFile) {
        parent.push({ name, path: current, kind: "file", children: [] });
        continue;
      }
      let folder = folders.get(current);
      if (!folder) {
        folder = { name, path: current, kind: "folder", children: [] };
        folders.set(current, folder);
        parent.push(folder);
      }
      parent = folder.children;
      prefix = current;
    }
  }
  sortTree(root);
  return root;
}

export function ancestorFolders(filePath: string): string[] {
  const parts = filePath.split("/").filter(Boolean);
  const folders: string[] = [];
  let prefix = "";
  for (let index = 0; index < parts.length - 1; index += 1) {
    prefix = prefix ? `${prefix}/${parts[index]}` : parts[index];
    folders.push(prefix);
  }
  return folders;
}

function sortTree(nodes: FileTreeNode[]): void {
  nodes.sort((left, right) => {
    if (left.kind !== right.kind) return left.kind === "folder" ? -1 : 1;
    return left.name.localeCompare(right.name);
  });
  for (const node of nodes) {
    if (node.kind === "folder") sortTree(node.children);
  }
}

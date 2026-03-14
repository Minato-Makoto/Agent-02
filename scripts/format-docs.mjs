#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const docsDir = path.join(root, "docs");
const mode = process.argv.includes("--check") ? "--check" : "--write";

/**
 * @param {string} dir
 * @returns {string[]}
 */
function collectMarkdownFiles(dir) {
  if (!fs.existsSync(dir)) {
    return [];
  }

  /** @type {string[]} */
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectMarkdownFiles(fullPath));
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".md")) {
      results.push(fullPath);
    }
  }
  return results;
}

const files = [
  ...collectMarkdownFiles(docsDir),
  path.join(root, "README.md"),
  path.join(root, "README.vi.md"),
].filter((filePath, index, all) => fs.existsSync(filePath) && all.indexOf(filePath) === index);

if (files.length === 0) {
  process.exit(0);
}

const oxfmtBin = process.platform === "win32" ? "oxfmt.CMD" : "oxfmt";
const result = spawnSync(oxfmtBin, [mode, ...files], {
  cwd: root,
  stdio: "inherit",
  shell: false,
});

process.exit(result.status ?? 0);

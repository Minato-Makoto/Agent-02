#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const gitDir = path.join(root, ".git");

if (!fs.existsSync(gitDir)) {
  process.exit(0);
}

const probe = spawnSync("git", ["rev-parse", "--is-inside-work-tree"], {
  cwd: root,
  stdio: "ignore",
  shell: process.platform === "win32",
});

if (probe.status !== 0) {
  process.exit(0);
}

const result = spawnSync("git", ["config", "core.hooksPath", "git-hooks"], {
  cwd: root,
  stdio: "inherit",
  shell: process.platform === "win32",
});

process.exit(result.status ?? 0);

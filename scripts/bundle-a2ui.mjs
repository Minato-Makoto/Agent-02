import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HASH_FILE = path.join(ROOT_DIR, "src/canvas-host/a2ui/.bundle.hash");
const OUTPUT_FILE = path.join(ROOT_DIR, "src/canvas-host/a2ui/a2ui.bundle.js");
const A2UI_RENDERER_DIR = path.join(ROOT_DIR, "vendor/a2ui/renderers/lit");
const A2UI_APP_DIR = path.join(ROOT_DIR, "apps/shared/OpenClawKit/Tools/CanvasA2UI");
const INPUT_PATHS = [
  path.join(ROOT_DIR, "package.json"),
  path.join(ROOT_DIR, "pnpm-lock.yaml"),
  A2UI_RENDERER_DIR,
  A2UI_APP_DIR,
];

function quoteForCmd(arg) {
  if (!/[\s"]/u.test(arg)) {
    return arg;
  }
  return `"${arg.replace(/"/g, '""')}"`;
}

function runCommand(command, args, cwd = ROOT_DIR) {
  const comspec = process.env.ComSpec || "cmd.exe";
  const fullCommand =
    `${quoteForCmd(command)} ${args.map((arg) => quoteForCmd(arg)).join(" ")}`.trim();
  const result = spawnSync(comspec, ["/d", "/s", "/c", fullCommand], {
    cwd,
    stdio: "inherit",
    windowsHide: true,
  });

  if (result.error) {
    throw result.error;
  }
  if ((result.status ?? 1) !== 0) {
    throw new Error(`Command failed: ${fullCommand}`);
  }
}

function runPnpm(args, cwd) {
  runCommand("corepack", ["pnpm", ...args], cwd);
}

function runNodeScript(scriptPath, args) {
  if (!fs.existsSync(scriptPath)) {
    throw new Error(`Missing local script: ${scriptPath}`);
  }
  const result = spawnSync(process.execPath, [scriptPath, ...args], {
    cwd: ROOT_DIR,
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error) {
    throw result.error;
  }
  if ((result.status ?? 1) !== 0) {
    throw new Error(`Command failed: node ${scriptPath}`);
  }
}

async function pathExists(targetPath) {
  try {
    await fsp.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

async function walk(entryPath, files) {
  const stat = await fsp.stat(entryPath);
  if (stat.isDirectory()) {
    const entries = await fsp.readdir(entryPath);
    for (const entry of entries) {
      await walk(path.join(entryPath, entry), files);
    }
    return;
  }
  files.push(entryPath);
}

async function computeHash() {
  const files = [];
  for (const inputPath of INPUT_PATHS) {
    await walk(inputPath, files);
  }

  files.sort((left, right) => {
    const normalizedLeft = path.relative(ROOT_DIR, left).split(path.sep).join("/");
    const normalizedRight = path.relative(ROOT_DIR, right).split(path.sep).join("/");
    return normalizedLeft.localeCompare(normalizedRight);
  });

  const hash = createHash("sha256");
  for (const filePath of files) {
    const relativePath = path.relative(ROOT_DIR, filePath).split(path.sep).join("/");
    hash.update(relativePath);
    hash.update("\0");
    hash.update(await fsp.readFile(filePath));
    hash.update("\0");
  }
  return hash.digest("hex");
}

async function main() {
  const hasRendererDir = await pathExists(A2UI_RENDERER_DIR);
  const hasAppDir = await pathExists(A2UI_APP_DIR);
  if (!hasRendererDir || !hasAppDir) {
    if (await pathExists(OUTPUT_FILE)) {
      console.log("A2UI sources missing; keeping prebuilt bundle.");
      return;
    }
    throw new Error(`A2UI sources missing and no prebuilt bundle found at: ${OUTPUT_FILE}`);
  }

  const currentHash = await computeHash();
  if ((await pathExists(HASH_FILE)) && (await pathExists(OUTPUT_FILE))) {
    const previousHash = (await fsp.readFile(HASH_FILE, "utf8")).trim();
    if (previousHash === currentHash) {
      console.log("A2UI bundle up to date; skipping.");
      return;
    }
  }

  runNodeScript(path.join(ROOT_DIR, "node_modules/typescript/bin/tsc"), [
    "-p",
    path.join(A2UI_RENDERER_DIR, "tsconfig.json"),
  ]);
  runPnpm(["-s", "dlx", "rolldown", "-c", "rolldown.config.mjs"], A2UI_APP_DIR);

  await ensureHashDir();
  await fsp.writeFile(HASH_FILE, `${currentHash}\n`, "utf8");
}

async function ensureHashDir() {
  await fsp.mkdir(path.dirname(HASH_FILE), { recursive: true });
}

main().catch((error) => {
  console.error("A2UI bundling failed. Re-run with: pnpm canvas:a2ui:bundle");
  console.error("If this persists, verify pnpm deps and try again.");
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});

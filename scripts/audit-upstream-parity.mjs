#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const DEFAULT_TAG = "v2026.3.12";
const DEFAULT_OUT_DIR = "audit";
const TEXT_EXTENSIONS = new Set([
  ".bat",
  ".cjs",
  ".css",
  ".json",
  ".jsonc",
  ".js",
  ".md",
  ".mdx",
  ".mjs",
  ".sh",
  ".toml",
  ".ts",
  ".tsx",
  ".txt",
  ".yaml",
  ".yml",
]);
const IGNORE_DIRS = new Set([
  ".git",
  "node_modules",
  "dist",
  ".openclaw",
  ".turbo",
  ".next",
  ".cache",
  "coverage",
]);
const IGNORE_FILES = new Set(["pnpm-lock.yaml"]);
const RESOLVED_RESTORE_PATHS = [
  "docs/reference/templates/AGENTS.md",
  "docs/reference/templates/AGENTS.dev.md",
  "docs/reference/templates/BOOT.md",
  "docs/reference/templates/BOOTSTRAP.md",
  "docs/reference/templates/HEARTBEAT.md",
  "docs/reference/templates/IDENTITY.md",
  "docs/reference/templates/IDENTITY.dev.md",
  "docs/reference/templates/SOUL.md",
  "docs/reference/templates/SOUL.dev.md",
  "docs/reference/templates/TOOLS.md",
  "docs/reference/templates/TOOLS.dev.md",
  "docs/reference/templates/USER.md",
  "docs/reference/templates/USER.dev.md",
];

const KEEP_PATH_PATTERNS = [
  /^\.gitignore$/,
  /^\.markdownlint-cli2\.jsonc$/,
  /^\.oxfmtrc\.jsonc$/,
  /^\.oxlintrc\.json$/,
  /^AGENTS\.md$/,
  /^README\.md$/,
  /^README\.vi\.md$/,
  /^SECURITY\.md$/,
  /^audit\/upstream-parity\.openclaw-v2026\.3\.12\.(json|md)$/,
  /^docs\/docs\.json$/,
  /^docs\/index\.md$/,
  /^docs\/en\//,
  /^docs\/vi\//,
  /^git-hooks\/pre-commit$/,
  /^package\.json$/,
  /^pnpm-workspace\.yaml$/,
  /^run\.bat$/,
  /^run\.local\.bat$/,
  /^run\.local\.bat\.example$/,
  /^scripts\/agent02-(launcher|stop)\.mjs$/,
  /^scripts\/audit-upstream-parity\.mjs$/,
  /^scripts\/bundle-a2ui\.mjs$/,
  /^scripts\/check-cleanup-surface\.mjs$/,
  /^scripts\/check-docs-parity\.mjs$/,
  /^scripts\/configure-git-hooks\.mjs$/,
  /^scripts\/format-docs\.mjs$/,
  /^scripts\/pre-commit\/run-node-tool\.sh$/,
  /^scripts\/run-node\.mjs$/,
  /^scripts\/tsdown-build\.mjs$/,
  /^scripts\/ui\.js$/,
  /^src\/agents\/sandbox\/browser\.ts$/,
  /^src\/cli\/update-cli\.ts$/,
  /^src\/commands\/doctor-sandbox\.ts$/,
  /^src\/compat\/legacy-names\.ts$/,
  /^src\/infra\/scripts-modules\.d\.ts$/,
  /^src\/canvas-host\/a2ui\/\.bundle\.hash$/,
  /^src\/canvas-host\/a2ui\/a2ui\.bundle\.js$/,
  /^stop\.bat$/,
  /^ui\/src\/i18n\/lib\/registry\.ts$/,
  /^ui\/src\/i18n\/lib\/types\.ts$/,
  /^ui\/src\/i18n\/locales\/en\.ts$/,
  /^ui\/src\/i18n\/locales\/vi\.ts$/,
  /^ui\/src\/i18n\/test\/translate\.test\.ts$/,
  /^vitest\.config\.ts$/,
];

const REFERENCE_RULES = [
  {
    category: "deleted-mobile-mac-paths",
    pattern: /\b(?:apps\/android|apps\/ios|apps\/macos|Swabble)\b/g,
    allowlist: [
      /^audit\/upstream-parity\.openclaw-v2026\.3\.12\.(json|md)$/,
      /^extensions\/diffs\/assets\/viewer-runtime\.js$/,
      /^scripts\/audit-upstream-parity\.mjs$/,
      /^scripts\/check-cleanup-surface\.mjs$/,
    ],
  },
  {
    category: "deleted-container-packaging-paths",
    pattern:
      /\b(?:Dockerfile(?:\.[A-Za-z0-9-]+)?|docker-compose(?:\.[A-Za-z0-9-]+)?\.yml|scripts\/docker|scripts\/e2e|scripts\/k8s|scripts\/podman|scripts\/systemd|scripts\/sandbox-browser-setup\.sh|scripts\/sandbox-common-setup\.sh|scripts\/sandbox-setup\.sh|scripts\/setup-auth-system\.sh|scripts\/auth-monitor\.sh|scripts\/shell-helpers|openclaw\.podman\.env|setup-podman\.sh|fly\.private\.toml|fly\.toml|render\.yaml)\b/g,
    allowlist: [
      /^audit\/upstream-parity\.openclaw-v2026\.3\.12\.(json|md)$/,
      /^extensions\/diffs\/assets\/viewer-runtime\.js$/,
      /^git-hooks\/pre-commit$/,
      /^scripts\/audit-upstream-parity\.mjs$/,
      /^scripts\/check-cleanup-surface\.mjs$/,
    ],
  },
  {
    category: "deleted-release-doc-paths",
    pattern:
      /\b(?:docs\/reference\/RELEASING\.md|docs\/platforms\/mac\/release\.md|docs\/install\/updating\.md|appcast\.xml)\b/g,
    allowlist: [
      /^audit\/upstream-parity\.openclaw-v2026\.3\.12\.(json|md)$/,
      /^scripts\/audit-upstream-parity\.mjs$/,
    ],
  },
  {
    category: "legacy-alt-product-names",
    pattern: /\b(?:clawdbot|moltbot)\b/g,
    allowlist: [
      /^audit\/upstream-parity\.openclaw-v2026\.3\.12\.(json|md)$/,
      /^scripts\/audit-upstream-parity\.mjs$/,
      /^extensions\/tlon\/src\//,
      /^skills\/gh-issues\/SKILL\.md$/,
      /^src\/agents\//,
      /^src\/commands\/doctor-.*\.ts$/,
      /^src\/commands\/doctor-.*\.test\.ts$/,
      /^src\/config\/paths(\.test)?\.ts$/,
      /^src\/daemon\//,
      /^src\/gateway\/server-methods\/(agent|agent-timestamp|chat)\.ts$/,
      /^src\/infra\/state-migrations\.state-dir\.test\.ts$/,
      /^src\/memory\/batch-voyage\.ts$/,
      /^test\/cli-json-stdout\.e2e\.test\.ts$/,
    ],
  },
];

function parseArgs(argv) {
  const args = {
    outDir: DEFAULT_OUT_DIR,
    tag: DEFAULT_TAG,
    upstream: process.env.OPENCLAW_UPSTREAM_DIR ?? "",
    write: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const current = argv[i];
    if (current === "--write") {
      args.write = true;
      continue;
    }
    if (current === "--upstream") {
      args.upstream = argv[i + 1] ?? "";
      i += 1;
      continue;
    }
    if (current === "--tag") {
      args.tag = argv[i + 1] ?? DEFAULT_TAG;
      i += 1;
      continue;
    }
    if (current === "--out-dir") {
      args.outDir = argv[i + 1] ?? DEFAULT_OUT_DIR;
      i += 1;
    }
  }
  return args;
}

function normalizePath(relPath) {
  return relPath.replaceAll("\\", "/");
}

function walkFiles(rootDir) {
  const files = new Map();
  const stack = [rootDir];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) {
      continue;
    }
    const entries = fs.readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      if (IGNORE_DIRS.has(entry.name)) {
        continue;
      }
      const absolutePath = path.join(current, entry.name);
      const relPath = normalizePath(path.relative(rootDir, absolutePath));
      if (entry.isDirectory()) {
        stack.push(absolutePath);
        continue;
      }
      if (IGNORE_FILES.has(entry.name)) {
        continue;
      }
      files.set(relPath, absolutePath);
    }
  }
  return files;
}

function sha256(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function matchesAny(relPath, patterns) {
  return patterns.some((pattern) => pattern.test(relPath));
}

function classifyDiff(kind, relPath) {
  if (relPath.startsWith("docs/reference/templates/")) {
    return "restore";
  }
  if (matchesAny(relPath, KEEP_PATH_PATTERNS)) {
    return "keep";
  }
  if (kind === "only-upstream") {
    return "keep";
  }
  return "finish_cleanup";
}

function isTextFile(relPath) {
  const ext = path.extname(relPath).toLowerCase();
  return TEXT_EXTENSIONS.has(ext) || !ext;
}

function scanDanglingReferences(fileMap) {
  const allowlisted = [];
  const unresolved = [];
  for (const [relPath, absolutePath] of fileMap.entries()) {
    if (!isTextFile(relPath)) {
      continue;
    }
    let content = "";
    try {
      content = fs.readFileSync(absolutePath, "utf8");
    } catch {
      continue;
    }
    for (const rule of REFERENCE_RULES) {
      const matches = Array.from(content.matchAll(rule.pattern), (match) => match[0]);
      if (matches.length === 0) {
        continue;
      }
      const entry = {
        path: relPath,
        category: rule.category,
        matches: Array.from(new Set(matches)).sort(),
      };
      if (matchesAny(relPath, rule.allowlist)) {
        allowlisted.push(entry);
      } else {
        unresolved.push(entry);
      }
    }
  }
  allowlisted.sort((a, b) => a.path.localeCompare(b.path) || a.category.localeCompare(b.category));
  unresolved.sort((a, b) => a.path.localeCompare(b.path) || a.category.localeCompare(b.category));
  return { allowlisted, unresolved };
}

function buildReport(args) {
  if (!args.upstream) {
    throw new Error(
      "Missing upstream source. Set OPENCLAW_UPSTREAM_DIR or pass --upstream <path>.",
    );
  }
  const upstreamPath = path.resolve(args.upstream);
  if (!fs.existsSync(upstreamPath)) {
    throw new Error(`Upstream directory does not exist: ${upstreamPath}`);
  }

  const localFiles = walkFiles(ROOT);
  const upstreamFiles = walkFiles(upstreamPath);
  const onlyUpstream = [];
  const onlyLocal = [];
  const changedCommon = [];
  const common = [];

  for (const relPath of upstreamFiles.keys()) {
    if (!localFiles.has(relPath)) {
      onlyUpstream.push(relPath);
      continue;
    }
    common.push(relPath);
  }
  for (const relPath of localFiles.keys()) {
    if (!upstreamFiles.has(relPath)) {
      onlyLocal.push(relPath);
    }
  }
  for (const relPath of common) {
    const localPath = localFiles.get(relPath);
    const upstreamFile = upstreamFiles.get(relPath);
    if (!localPath || !upstreamFile) {
      continue;
    }
    const localStat = fs.statSync(localPath);
    const upstreamStat = fs.statSync(upstreamFile);
    if (localStat.size !== upstreamStat.size || sha256(localPath) !== sha256(upstreamFile)) {
      changedCommon.push(relPath);
    }
  }

  onlyUpstream.sort();
  onlyLocal.sort();
  changedCommon.sort();

  const classified = {
    restore: {
      onlyUpstream: onlyUpstream.filter(
        (relPath) => classifyDiff("only-upstream", relPath) === "restore",
      ),
      onlyLocal: onlyLocal.filter((relPath) => classifyDiff("only-local", relPath) === "restore"),
      changed: changedCommon.filter((relPath) => classifyDiff("changed", relPath) === "restore"),
    },
    keep: {
      onlyUpstream: onlyUpstream.filter(
        (relPath) => classifyDiff("only-upstream", relPath) === "keep",
      ),
      onlyLocal: onlyLocal.filter((relPath) => classifyDiff("only-local", relPath) === "keep"),
      changed: changedCommon.filter((relPath) => classifyDiff("changed", relPath) === "keep"),
    },
    finish_cleanup: {
      onlyUpstream: onlyUpstream.filter(
        (relPath) => classifyDiff("only-upstream", relPath) === "finish_cleanup",
      ),
      onlyLocal: onlyLocal.filter(
        (relPath) => classifyDiff("only-local", relPath) === "finish_cleanup",
      ),
      changed: changedCommon.filter(
        (relPath) => classifyDiff("changed", relPath) === "finish_cleanup",
      ),
    },
  };

  const danglingReferences = scanDanglingReferences(localFiles);
  const generatedAt = new Date().toISOString();
  return {
    baseline: {
      repoRoot: ROOT,
      upstreamPath,
      upstreamTag: args.tag,
      generatedAt,
    },
    summary: {
      onlyInUpstream: onlyUpstream.length,
      onlyInLocal: onlyLocal.length,
      changedCommon: changedCommon.length,
      resolvedRestorePaths: RESOLVED_RESTORE_PATHS.length,
      classified: {
        restore:
          classified.restore.onlyUpstream.length +
          classified.restore.onlyLocal.length +
          classified.restore.changed.length,
        keep:
          classified.keep.onlyUpstream.length +
          classified.keep.onlyLocal.length +
          classified.keep.changed.length,
        finish_cleanup:
          classified.finish_cleanup.onlyUpstream.length +
          classified.finish_cleanup.onlyLocal.length +
          classified.finish_cleanup.changed.length,
      },
      danglingReferences: {
        unresolved: danglingReferences.unresolved.length,
        allowlisted: danglingReferences.allowlisted.length,
      },
    },
    resolvedRestores: {
      restoredFromUpstreamThisPass: RESOLVED_RESTORE_PATHS,
    },
    classifiedDiffs: classified,
    danglingReferences,
  };
}

function formatSummary(report) {
  const lines = [
    `# Upstream Parity Audit (${report.baseline.upstreamTag})`,
    "",
    `Generated: ${report.baseline.generatedAt}`,
    "",
    "## Summary",
    "",
    `- Only in upstream: ${report.summary.onlyInUpstream}`,
    `- Only in local fork: ${report.summary.onlyInLocal}`,
    `- Changed on common paths: ${report.summary.changedCommon}`,
    `- Confirmed runtime restores completed this pass: ${report.summary.resolvedRestorePaths}`,
    `- Classified as keep: ${report.summary.classified.keep}`,
    `- Classified as finish_cleanup: ${report.summary.classified.finish_cleanup}`,
    `- Classified as restore still pending: ${report.summary.classified.restore}`,
    `- Dangling references unresolved: ${report.summary.danglingReferences.unresolved}`,
    `- Dangling references allowlisted/documented: ${report.summary.danglingReferences.allowlisted}`,
    "",
    "## Resolved Restore Set",
    "",
    ...report.resolvedRestores.restoredFromUpstreamThisPass.map((relPath) => `- \`${relPath}\``),
    "",
    "## Remaining Finish-Cleanup Diffs",
    "",
  ];

  const finishCleanup = [
    ...report.classifiedDiffs.finish_cleanup.changed,
    ...report.classifiedDiffs.finish_cleanup.onlyLocal,
    ...report.classifiedDiffs.finish_cleanup.onlyUpstream,
  ];
  if (finishCleanup.length === 0) {
    lines.push("- None");
  } else {
    for (const relPath of finishCleanup.slice(0, 40)) {
      lines.push(`- \`${relPath}\``);
    }
    if (finishCleanup.length > 40) {
      lines.push(`- ... and ${finishCleanup.length - 40} more (see JSON manifest)`);
    }
  }

  lines.push("", "## Dangling References", "");
  if (report.danglingReferences.unresolved.length === 0) {
    lines.push("- No unresolved references to deleted surfaces remain.");
  } else {
    for (const entry of report.danglingReferences.unresolved.slice(0, 40)) {
      lines.push(`- \`${entry.path}\` → ${entry.category}: ${entry.matches.join(", ")}`);
    }
    if (report.danglingReferences.unresolved.length > 40) {
      lines.push(
        `- ... and ${report.danglingReferences.unresolved.length - 40} more unresolved entries (see JSON manifest)`,
      );
    }
  }

  lines.push("", "## Allowlisted Compatibility References", "");
  if (report.danglingReferences.allowlisted.length === 0) {
    lines.push("- None");
  } else {
    for (const entry of report.danglingReferences.allowlisted.slice(0, 40)) {
      lines.push(`- \`${entry.path}\` → ${entry.category}: ${entry.matches.join(", ")}`);
    }
    if (report.danglingReferences.allowlisted.length > 40) {
      lines.push(
        `- ... and ${report.danglingReferences.allowlisted.length - 40} more allowlisted entries (see JSON manifest)`,
      );
    }
  }

  return `${lines.join("\n")}\n`;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const report = buildReport(args);
  const summary = formatSummary(report);
  if (args.write) {
    const outDir = path.join(ROOT, args.outDir);
    fs.mkdirSync(outDir, { recursive: true });
    const jsonPath = path.join(outDir, "upstream-parity.openclaw-v2026.3.12.json");
    const mdPath = path.join(outDir, "upstream-parity.openclaw-v2026.3.12.md");
    fs.writeFileSync(jsonPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    fs.writeFileSync(mdPath, summary, "utf8");
    console.log(`wrote ${path.relative(ROOT, jsonPath)}`);
    console.log(`wrote ${path.relative(ROOT, mdPath)}`);
    return;
  }
  console.log(JSON.stringify(report, null, 2));
}

main();

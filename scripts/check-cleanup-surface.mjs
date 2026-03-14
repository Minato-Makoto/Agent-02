#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const PACKAGE_JSON_PATH = path.join(ROOT, "package.json");

const FORBIDDEN_PATHS = [
  ".github",
  ".agent",
  ".agents",
  "changelog",
  "docs/.i18n",
  "docs/ja-JP",
  "docs/zh-CN",
  ".swiftformat",
  ".swiftlint.yml",
  "CLAUDE.md",
  "Swabble",
  "apps/android",
  "apps/ios",
  "apps/macos",
  "docker-compose.yml",
  "docker-setup.sh",
  "Dockerfile",
  "Dockerfile.sandbox",
  "Dockerfile.sandbox-browser",
  "Dockerfile.sandbox-common",
  "openclaw.podman.env",
  "setup-podman.sh",
  "fly.private.toml",
  "fly.toml",
  "render.yaml",
  "scripts/docker",
  "scripts/e2e",
  "scripts/k8s",
  "scripts/podman",
  "scripts/systemd",
  "scripts/docs-i18n",
  "scripts/auth-monitor.sh",
  "scripts/install.sh",
  "scripts/install.ps1",
  "scripts/protocol-gen-swift.ts",
  "scripts/run-openclaw-podman.sh",
  "scripts/sandbox-browser-setup.sh",
  "scripts/sandbox-common-setup.sh",
  "scripts/sandbox-setup.sh",
  "scripts/setup-auth-system.sh",
  "scripts/shell-helpers",
  "scripts/termux-auth-widget.sh",
  "scripts/termux-quick-auth.sh",
  "scripts/termux-sync-widget.sh",
  "docs/reference/templates/CLAUDE.md",
  "src/config/talk-defaults.test.ts",
  "src/cron/cron-protocol-conformance.test.ts",
  "src/docker-build-cache.test.ts",
  "src/docker-image-digests.test.ts",
  "src/docker-setup.e2e.test.ts",
  "src/dockerfile.test.ts",
  "src/infra/host-env-security.policy-parity.test.ts",
  "src/scripts/ci-changed-scope.test.ts",
];

const FORBIDDEN_SCRIPT_PATTERNS = [
  /^android:/,
  /^ios:/,
  /^mac:/,
  /^build:docker$/,
  /^check:host-env-policy:swift$/,
  /^docs:bin$/,
  /^docs:list$/,
  /^docs:spellcheck/,
  /^format:swift$/,
  /^lint:swift$/,
  /^release:/,
  /^test:docker:/,
  /^test:install:/,
];

/** @type {string[]} */
const failures = [];

for (const relPath of FORBIDDEN_PATHS) {
  if (fs.existsSync(path.join(ROOT, relPath))) {
    failures.push(`forbidden path still exists: ${relPath}`);
  }
}

const appsDir = path.join(ROOT, "apps");
if (fs.existsSync(appsDir)) {
  const appEntries = fs
    .readdirSync(appsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name);
  for (const name of appEntries) {
    if (name !== "shared") {
      failures.push(`unexpected apps directory remains: apps/${name}`);
    }
  }
}

if (fs.existsSync(path.join(ROOT, "packages"))) {
  const packageEntries = fs.readdirSync(path.join(ROOT, "packages"), { withFileTypes: true });
  if (packageEntries.length > 0) {
    failures.push("packages/ should be empty or removed in the Windows-only fork");
  }
}

if (!fs.existsSync(PACKAGE_JSON_PATH)) {
  failures.push("missing package.json");
} else {
  const pkg = JSON.parse(fs.readFileSync(PACKAGE_JSON_PATH, "utf8"));
  const scripts = pkg.scripts ?? {};
  for (const name of Object.keys(scripts)) {
    if (FORBIDDEN_SCRIPT_PATTERNS.some((pattern) => pattern.test(name))) {
      failures.push(`forbidden package.json script remains: ${name}`);
    }
  }
}

if (!fs.existsSync(path.join(ROOT, "README.md"))) {
  failures.push("missing README.md");
}

if (!fs.existsSync(path.join(ROOT, "README.vi.md"))) {
  failures.push("missing README.vi.md");
}

const requiredWorkspaceTemplates = [
  "AGENTS.md",
  "AGENTS.dev.md",
  "BOOT.md",
  "HEARTBEAT.md",
  "BOOTSTRAP.md",
  "IDENTITY.md",
  "IDENTITY.dev.md",
  "SOUL.md",
  "SOUL.dev.md",
  "TOOLS.md",
  "TOOLS.dev.md",
  "USER.md",
  "USER.dev.md",
];
const workspaceTemplateDir = path.join(ROOT, "docs", "reference", "templates");
if (!fs.existsSync(workspaceTemplateDir)) {
  failures.push("missing docs/reference/templates");
} else {
  for (const templateName of requiredWorkspaceTemplates) {
    if (!fs.existsSync(path.join(workspaceTemplateDir, templateName))) {
      failures.push(
        `missing required workspace template: docs/reference/templates/${templateName}`,
      );
    }
  }
}

const uiLocaleDir = path.join(ROOT, "ui", "src", "i18n", "locales");
if (!fs.existsSync(uiLocaleDir)) {
  failures.push("missing ui/src/i18n/locales");
} else {
  const localeFiles = fs
    .readdirSync(uiLocaleDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".ts"))
    .map((entry) => entry.name)
    .sort();
  const expectedLocaleFiles = ["en.ts", "vi.ts"];
  if (localeFiles.length !== expectedLocaleFiles.length) {
    failures.push(
      `ui locales must be exactly ${expectedLocaleFiles.join(", ")}; found ${localeFiles.join(", ")}`,
    );
  } else {
    for (const expected of expectedLocaleFiles) {
      if (!localeFiles.includes(expected)) {
        failures.push(`missing expected UI locale file: ui/src/i18n/locales/${expected}`);
      }
    }
  }
}

if (failures.length > 0) {
  for (const failure of failures) {
    console.error(`check-cleanup-surface: ${failure}`);
  }
  process.exit(1);
}

console.log("check-cleanup-surface: ok");

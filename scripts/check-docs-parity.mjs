#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const DOCS_DIR = path.join(ROOT, "docs");
const DOCS_JSON_PATH = path.join(DOCS_DIR, "docs.json");
const REQUIRED_LANGUAGES = ["en", "vi"];

function walkMarkdown(dir) {
  const files = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name.startsWith(".")) {
      continue;
    }
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkMarkdown(full));
      continue;
    }
    if (entry.isFile() && /\.(md|mdx)$/i.test(entry.name)) {
      files.push(full);
    }
  }
  return files;
}

function toSlug(locale, absolutePath) {
  const rel = path.relative(path.join(DOCS_DIR, locale), absolutePath).replace(/\\/g, "/");
  return rel.replace(/\.(md|mdx)$/i, "");
}

function collectLocaleFileSlugs(locale) {
  const localeDir = path.join(DOCS_DIR, locale);
  if (!fs.existsSync(localeDir)) {
    throw new Error(`Missing docs locale directory: ${localeDir}`);
  }
  return new Set(walkMarkdown(localeDir).map((file) => toSlug(locale, file)));
}

function collectPages(value, out = []) {
  if (Array.isArray(value)) {
    for (const item of value) {
      collectPages(item, out);
    }
    return out;
  }
  if (!value || typeof value !== "object") {
    return out;
  }
  if (Array.isArray(value.pages)) {
    for (const page of value.pages) {
      if (typeof page === "string") {
        out.push(page);
      }
    }
  }
  for (const nested of Object.values(value)) {
    collectPages(nested, out);
  }
  return out;
}

if (!fs.existsSync(DOCS_JSON_PATH)) {
  console.error("check-docs-parity: missing docs/docs.json");
  process.exit(1);
}

if (!fs.existsSync(path.join(DOCS_DIR, "index.md"))) {
  console.error("check-docs-parity: missing docs/index.md");
  process.exit(1);
}

const docsConfig = JSON.parse(fs.readFileSync(DOCS_JSON_PATH, "utf8"));
const languages = docsConfig.navigation?.languages;
if (!Array.isArray(languages)) {
  console.error("check-docs-parity: docs.json is missing navigation.languages");
  process.exit(1);
}

const failures = [];

for (const locale of REQUIRED_LANGUAGES) {
  const languageConfig = languages.find((item) => item?.language === locale);
  if (!languageConfig) {
    failures.push(`docs.json is missing navigation for language "${locale}"`);
    continue;
  }

  const fileSlugs = collectLocaleFileSlugs(locale);
  if (fileSlugs.size === 0) {
    failures.push(`docs/${locale} has no markdown pages`);
    continue;
  }

  const navPages = new Set();
  for (const page of collectPages(languageConfig.tabs ?? [])) {
    if (!page.startsWith(`${locale}/`)) {
      failures.push(`docs.json page "${page}" is not namespaced under ${locale}/`);
      continue;
    }
    navPages.add(page.slice(locale.length + 1));
  }

  for (const slug of fileSlugs) {
    if (!navPages.has(slug)) {
      failures.push(`docs/${locale}/${slug}.md is missing from docs.json navigation`);
    }
  }

  for (const slug of navPages) {
    if (!fileSlugs.has(slug)) {
      failures.push(`docs.json references missing docs/${locale}/${slug}.md`);
    }
  }
}

if (failures.length === 0) {
  const [enSlugs, viSlugs] = REQUIRED_LANGUAGES.map((locale) => collectLocaleFileSlugs(locale));
  for (const slug of enSlugs) {
    if (!viSlugs.has(slug)) {
      failures.push(`docs/vi is missing slug "${slug}"`);
    }
  }
  for (const slug of viSlugs) {
    if (!enSlugs.has(slug)) {
      failures.push(`docs/en is missing slug "${slug}"`);
    }
  }
}

if (failures.length > 0) {
  for (const failure of failures) {
    console.error(`check-docs-parity: ${failure}`);
  }
  process.exit(1);
}

const count = collectLocaleFileSlugs("en").size;
console.log(`check-docs-parity: ok (${count} mirrored slugs, languages=${REQUIRED_LANGUAGES.join(",")})`);

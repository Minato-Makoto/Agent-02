#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo
echo "  Agent-02 v4.20"
echo "  Private AI gateway for local-first use"
echo

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 22+ is required."
  echo "Install it from https://nodejs.org/ and run this script again."
  exit 1
fi

echo "  [OK] Node.js $(node -v)"
echo "  [*] Installing dependencies..."
npm install --no-fund --no-audit

echo "  [*] Building..."
npm run build

mkdir -p data/workspace data/instructions

echo
echo "  [OK] Agent-02 is ready."
echo "  Open: http://localhost:8420"
echo "  Start: npm start"
echo

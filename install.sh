#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
# Agent-02 — Quick Install Script
# ═══════════════════════════════════════════════════
set -e

echo ""
echo "  ⚡ Agent-02 Installer"
echo "  ════════════════════════════════════"
echo ""

# Check Node.js
if ! command -v node &> /dev/null; then
  echo "  [!] Node.js not found. Installing via nvm..."
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
  nvm install 22
fi

NODE_VERSION=$(node -v)
echo "  [OK] Node.js $NODE_VERSION"

# Clone or update
INSTALL_DIR="${AGENT02_DIR:-$HOME/agent-02}"
if [ -d "$INSTALL_DIR" ]; then
  echo "  [*] Updating existing installation..."
  cd "$INSTALL_DIR"
  git pull --ff-only 2>/dev/null || true
else
  echo "  [*] Cloning Agent-02..."
  git clone https://github.com/yourname/agent-02.git "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# Install deps
echo "  [*] Installing dependencies..."
npm install --no-fund --no-audit

# Build
echo "  [*] Building..."
npm run build

# Create symlink
if [ -w /usr/local/bin ]; then
  ln -sf "$INSTALL_DIR/dist/index.js" /usr/local/bin/agent02
  echo "  [OK] Installed 'agent02' command globally"
else
  echo "  [i] Add to PATH: export PATH=\"$INSTALL_DIR/dist:\$PATH\""
fi

echo ""
echo "  ════════════════════════════════════"
echo "  [OK] Agent-02 installed!"
echo "  [*] Run: npm start"
echo "  [*] Open: http://localhost:8080"
echo ""

#!/usr/bin/env bash
set -euo pipefail

REPO="yourname/agent-02"
INSTALL_DIR="${AGENT02_DIR:-$HOME/.agent02}"
BIN_DIR="${AGENT02_BIN_DIR:-$HOME/.local/bin}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

need_cmd curl
need_cmd tar

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

case "$OS" in
  linux*) OS="linux" ;;
  darwin*) OS="darwin" ;;
  *)
    echo "Unsupported OS for install.sh: $OS" >&2
    exit 1
    ;;
esac

ASSET="agent02-${OS}-${ARCH}.tar.gz"
URL="https://github.com/${REPO}/releases/latest/download/${ASSET}"

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

if curl -fsSL "$URL" -o "$TMP_DIR/$ASSET"; then
  tar -xzf "$TMP_DIR/$ASSET" -C "$INSTALL_DIR"
  chmod +x "$INSTALL_DIR/agent02"
else
  echo "[agent02] Prebuilt binary not found. Falling back to source build."
  need_cmd git
  need_cmd go

  if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" fetch --tags --force
    git -C "$INSTALL_DIR" pull --ff-only
  else
    rm -rf "$INSTALL_DIR"
    git clone "https://github.com/${REPO}.git" "$INSTALL_DIR"
  fi

  (cd "$INSTALL_DIR" && go build -trimpath -ldflags="-s -w" -o "$INSTALL_DIR/agent02" ./cmd/agent02)
fi

ln -sf "$INSTALL_DIR/agent02" "$BIN_DIR/agent02"

if ! echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
  echo "Add this to your shell profile:"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

echo "Installed: $BIN_DIR/agent02"
echo "Run: agent02 start"
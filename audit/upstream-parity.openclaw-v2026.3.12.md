# Upstream Parity Audit (v2026.3.12)

Generated: 2026-03-14T09:42:14.529Z

## Summary

- Only in upstream: 1625
- Only in local fork: 30
- Changed on common paths: 26
- Confirmed runtime restores completed this pass: 13
- Classified as keep: 1681
- Classified as finish_cleanup: 0
- Classified as restore still pending: 0
- Dangling references unresolved: 0
- Dangling references allowlisted/documented: 39

## Resolved Restore Set

- `docs/reference/templates/AGENTS.md`
- `docs/reference/templates/AGENTS.dev.md`
- `docs/reference/templates/BOOT.md`
- `docs/reference/templates/BOOTSTRAP.md`
- `docs/reference/templates/HEARTBEAT.md`
- `docs/reference/templates/IDENTITY.md`
- `docs/reference/templates/IDENTITY.dev.md`
- `docs/reference/templates/SOUL.md`
- `docs/reference/templates/SOUL.dev.md`
- `docs/reference/templates/TOOLS.md`
- `docs/reference/templates/TOOLS.dev.md`
- `docs/reference/templates/USER.md`
- `docs/reference/templates/USER.dev.md`

## Remaining Finish-Cleanup Diffs

- None

## Dangling References

- No unresolved references to deleted surfaces remain.

## Allowlisted Compatibility References

- `audit/upstream-parity.openclaw-v2026.3.12.json` → deleted-container-packaging-paths: Dockerfile, Dockerfile.qr-import, Dockerfile.sandbox, Dockerfile.sandbox-browser, Dockerfile.sandbox-common, docker-compose.yml, fly.private.toml, fly.toml, openclaw.podman.env, render.yaml, scripts/auth-monitor.sh, scripts/docker, scripts/e2e, scripts/k8s, scripts/podman, scripts/sandbox-browser-setup.sh, scripts/sandbox-common-setup.sh, scripts/sandbox-setup.sh, scripts/setup-auth-system.sh, scripts/shell-helpers, scripts/systemd, setup-podman.sh
- `audit/upstream-parity.openclaw-v2026.3.12.json` → deleted-mobile-mac-paths: Swabble, apps/android, apps/ios, apps/macos
- `audit/upstream-parity.openclaw-v2026.3.12.json` → deleted-release-doc-paths: appcast.xml, docs/install/updating.md, docs/platforms/mac/release.md, docs/reference/RELEASING.md
- `audit/upstream-parity.openclaw-v2026.3.12.json` → legacy-alt-product-names: clawdbot, moltbot
- `audit/upstream-parity.openclaw-v2026.3.12.md` → deleted-container-packaging-paths: Dockerfile, Dockerfile.sandbox, Dockerfile.sandbox-browser, Dockerfile.sandbox-common, docker-compose.yml, fly.private.toml, fly.toml, openclaw.podman.env, render.yaml, scripts/auth-monitor.sh, scripts/docker, scripts/e2e, scripts/k8s, scripts/podman, scripts/sandbox-browser-setup.sh, scripts/sandbox-common-setup.sh, scripts/sandbox-setup.sh, scripts/setup-auth-system.sh, scripts/shell-helpers, scripts/systemd, setup-podman.sh
- `audit/upstream-parity.openclaw-v2026.3.12.md` → deleted-mobile-mac-paths: Swabble, apps/android, apps/ios, apps/macos
- `audit/upstream-parity.openclaw-v2026.3.12.md` → legacy-alt-product-names: clawdbot, moltbot
- `extensions/diffs/assets/viewer-runtime.js` → deleted-container-packaging-paths: Dockerfile
- `extensions/tlon/src/monitor/index.ts` → legacy-alt-product-names: moltbot
- `extensions/tlon/src/settings.ts` → legacy-alt-product-names: moltbot
- `git-hooks/pre-commit` → deleted-container-packaging-paths: Dockerfile
- `scripts/audit-upstream-parity.mjs` → deleted-container-packaging-paths: Dockerfile
- `scripts/audit-upstream-parity.mjs` → deleted-mobile-mac-paths: Swabble
- `scripts/audit-upstream-parity.mjs` → legacy-alt-product-names: clawdbot, moltbot
- `scripts/check-cleanup-surface.mjs` → deleted-container-packaging-paths: Dockerfile, Dockerfile.sandbox, Dockerfile.sandbox-browser, Dockerfile.sandbox-common, docker-compose.yml, fly.private.toml, fly.toml, openclaw.podman.env, render.yaml, scripts/auth-monitor.sh, scripts/docker, scripts/e2e, scripts/k8s, scripts/podman, scripts/sandbox-browser-setup.sh, scripts/sandbox-common-setup.sh, scripts/sandbox-setup.sh, scripts/setup-auth-system.sh, scripts/shell-helpers, scripts/systemd, setup-podman.sh
- `scripts/check-cleanup-surface.mjs` → deleted-mobile-mac-paths: Swabble, apps/android, apps/ios, apps/macos
- `skills/gh-issues/SKILL.md` → legacy-alt-product-names: clawdbot
- `src/agents/pi-tools.create-openclaw-coding-tools.adds-claude-style-aliases-schemas-without-dropping-d.test.ts` → legacy-alt-product-names: moltbot
- `src/agents/sandbox/fs-bridge-mutation-helper.test.ts` → legacy-alt-product-names: moltbot
- `src/agents/sandbox/fs-bridge.test-helpers.ts` → legacy-alt-product-names: moltbot
- `src/agents/sandbox/fs-bridge.ts` → legacy-alt-product-names: moltbot
- `src/agents/system-prompt.test.ts` → legacy-alt-product-names: moltbot
- `src/agents/tools/gateway.test.ts` → legacy-alt-product-names: clawdbot
- `src/commands/doctor-config-flow.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/commands/doctor-gateway-services.test.ts` → legacy-alt-product-names: moltbot
- `src/commands/doctor-gateway-services.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/commands/doctor-state-migrations.test.ts` → legacy-alt-product-names: clawdbot
- `src/config/paths.test.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/config/paths.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/daemon/constants.test.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/daemon/constants.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/daemon/inspect.test.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/daemon/inspect.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/gateway/server-methods/agent-timestamp.ts` → legacy-alt-product-names: moltbot
- `src/gateway/server-methods/agent.ts` → legacy-alt-product-names: moltbot
- `src/gateway/server-methods/chat.ts` → legacy-alt-product-names: moltbot
- `src/infra/state-migrations.state-dir.test.ts` → legacy-alt-product-names: clawdbot, moltbot
- `src/memory/batch-voyage.ts` → legacy-alt-product-names: clawdbot
- `test/cli-json-stdout.e2e.test.ts` → legacy-alt-product-names: clawdbot

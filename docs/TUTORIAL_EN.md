# Tutorial

## 1. What You Get Today

Current Agent-02 does one thing:
- launch `llama-server.exe`

The default UI is the llama WebUI served by that process.

## 2. Start It

1. Put your GGUF files under the shared `models/` directory.
2. Copy `run.local.bat.example` to `run.local.bat` if you need local path overrides.
3. Run `run.bat`.

Default local URLs:
- WebUI: `http://127.0.0.1:8080`
- Health: `http://127.0.0.1:8080/health`
- Models: `http://127.0.0.1:8080/models`

## 3. What Agent-02 Does Not Add

This release does not add:
- a custom WebUI
- a custom gateway
- a custom chat session layer
- a custom model picker on top of llama

If the feature already exists in standalone llama, Agent-02 intentionally leaves it there.

## 4. Local Overrides

Use `run.local.bat` for machine-specific changes such as:
- `SERVER_EXE`
- `MODELS_DIR`
- `HOST`
- `PORT`
- `MODELS_MAX`
- `CTX_SIZE`
- `GPU_LAYERS`

## 5. Troubleshooting

If startup fails:
- read the launcher output for `Reason`, `Command`, and `llama-server stderr (tail)`
- check whether `HOST:PORT` is already occupied
- verify `SERVER_EXE` and `MODELS_DIR`

## 6. What Comes Next

Future work does not start from UI duplication.

It starts from the TODO roadmap in `docs/TODO_RUNTIME_DIFF.md`, and only for features that standalone llama does not already own.

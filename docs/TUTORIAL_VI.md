# Tutorial

## 1. Hien Tai Co Gi

Agent-02 hien tai chi lam mot viec:
- khoi dong `llama-server.exe`

UI mac dinh la llama WebUI do chinh process nay serve.

## 2. Cac Buoc Chay

1. Dat file GGUF vao thu muc `models/`.
2. Copy `run.local.bat.example` thanh `run.local.bat` neu can override theo may.
3. Chay `run.bat`.

URL mac dinh:
- WebUI: `http://127.0.0.1:8080`
- Health: `http://127.0.0.1:8080/health`
- Models: `http://127.0.0.1:8080/models`

## 3. Agent-02 Khong Them Gi O Wave Nay

Release nay khong them:
- WebUI rieng
- gateway rieng
- lop chat session rieng
- lop model picker de len tren llama

Neu standalone llama da co san tinh nang thi Agent-02 co y khong duplicate.

## 4. Local Overrides

Dung `run.local.bat` cho cac thay doi theo may, vi du:
- `SERVER_EXE`
- `MODELS_DIR`
- `HOST`
- `PORT`
- `MODELS_MAX`
- `CTX_SIZE`
- `GPU_LAYERS`

## 5. Troubleshooting

Neu khoi dong loi:
- doc output cua launcher o `Reason`, `Command`, va `llama-server stderr (tail)`
- kiem tra `HOST:PORT` co dang bi process khac chiem hay khong
- xac minh `SERVER_EXE` va `MODELS_DIR`

## 6. Buoc Tiep Theo

Cong viec tiep theo khong bat dau tu viec duplicate UI.

No phai bat dau tu TODO roadmap trong `docs/TODO_RUNTIME_DIFF.md`, va chi danh cho nhung phan standalone llama chua so huu.

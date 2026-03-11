# Agent-02 Tutorial (VI)

Tai lieu nay mo ta luong su dung duoc ho tro cua Agent-02: Gateway, WebUI va quan ly channel.

## 1. Cau truc thu muc khuyen nghi

```text
D:\AI Agent\
|- Agent-02\
|- llama.cpp\llama-server.exe
`- models\
   |- model-a.gguf
   `- model-b.gguf
```

Gia tri launcher mac dinh:

- `SERVER_EXE=..\llama.cpp\llama-server.exe`
- `MODELS_DIR=..\models`
- `GATEWAY_HOST=127.0.0.1`
- `GATEWAY_PORT=18789`
- `HOST=127.0.0.1`
- `PORT=8080`
- `REASONING_EFFORT=` (de trong mac dinh)
- `MAX_REQUESTS_PER_MINUTE=0` (tat gioi han mac dinh)

Neu may cua ban khac layout nay, dat override trong `run.local.bat`.

## 2. Khoi dong lan dau

1. Cai Python 3.10+.
2. Dam bao `llama-server.exe` da ton tai.
3. Dat mot hoac nhieu file GGUF vao `..\models`.
4. Chay `run.bat`.

Lan dau chay co the se tu cai dependency Python va Playwright Chromium.

## 3. Khi chay se co gi

`run.bat` se:

1. khoi dong `llama-server` o router mode
2. khoi dong Agent-02 Gateway
3. doi `/health` san sang
4. mo `http://127.0.0.1:18789/webchat` neu `AUTO_OPEN_BROWSER` khong bi tat

Neu Agent-02 da chay san tren gateway port do, launcher se reuse instance hien co va mo WebUI hien tai thay vi khoi dong them server moi.

URL huu ich:

- Health: `http://127.0.0.1:18789/health`
- WebUI: `http://127.0.0.1:18789/webchat`
- Web UI cua llama.cpp: `http://127.0.0.1:8080/`

## 4. Co ban ve WebUI

WebUI la giao dien van hanh chinh:

- cot trai: session va inbox
- giua: khung chat
- cot phai: `Models`, `Channels`, `Pairing`, `Settings`

Logical session mac dinh la `agent:main:main`.

Neu router chi co 1 model, Agent-02 se tu chon. Neu co nhieu model, session hien tai se bi chan cho toi khi ban chon model trong WebUI.

## 5. Cai dat channel

Channel duoc ho tro trong wave nay:

- Telegram
- Discord
- Zalo

Config channel duoc luu o `workspace/gateway/config.json`.

Ban co the cau hinh trong WebUI hoac dung env fallback:

- `TELEGRAM_BOT_TOKEN`
- `DISCORD_BOT_TOKEN`
- `ZALO_BOT_TOKEN`

WebUI khong hien lai secret sau khi da luu.

## 6. Pairing va kiem soat truy cap

Mac dinh DM dung `dmPolicy=pairing`.

Nghia la:

1. tin nhan DM dau tien bi chan
2. Agent-02 tra ve pairing code
3. ban approve hoac reject code trong WebUI > `Pairing`

Group va guild mac dinh fail-closed:

- `groupPolicy=allowlist`
- `requireMention=true`

## 7. Session routing

Khoa session trong wave nay:

- WebChat va DM da duoc approve: `agent:main:main`
- Telegram va Zalo group: `agent:main:<channel>:group:<id>`
- Discord guild channel: `agent:main:discord:channel:<id>`

`reset` tao transcript moi nhung giu nguyen logical route.

## 8. Lenh huu ich

```powershell
$env:PYTHONPATH = "src"
python -m agentforge.cli --help
python -m agentforge.cli gateway --help
python -m agentforge.cli gateway run --help
python -m agentforge.cli run --help
```

`agentforge run` chi con la alias deprecate tro toi `agentforge gateway run`.

## 9. Xu ly su co

### WebUI mo len nhung khong thay model

- kiem tra `MODELS_DIR`
- mo `http://127.0.0.1:8080/`
- xac nhan router tra duoc `GET /v1/models`

### WebUI khong tu mo

- dat `AUTO_OPEN_BROWSER=1`
- dam bao gateway len duoc `/health`

### `run.bat` hong sau khi sua

- giu CRLF line endings
- tranh luu `.bat` thanh LF-only

### Port `8080` dang bi chiem

- tat process dang dung port
- hoac override `PORT` trong `run.local.bat`

## 10. Kiem tra

```powershell
python -m pytest -q
python -m compileall -q src
$env:PYTHONPATH='src'; python -m agentforge.cli --help
$env:PYTHONPATH='src'; python -m agentforge.cli gateway --help
```

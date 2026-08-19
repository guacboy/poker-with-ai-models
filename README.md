# poker-with-ai-models

No-Limit Texas Hold'em against 5 AI opponents (Claude, OpenAI, DeepSeek, Gemini, Grok), each playing through its own API. Python/FastAPI backend (poker engine on [pokerkit](https://github.com/uoftcprg/pokerkit)), React frontend, local text-to-speech for AI trash talk via [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M).

## Tournament format

6-max, 100 BB starting stack, blinds increase every 10 hands, up to 3 buy-ins per player (human and AI alike, fixed rebuy size), no antes. All of this is tunable in [`backend/app/rules.py`](backend/app/rules.py).

## Setup

### Backend

```
cd backend
python -m venv .venv

# activate the venv -- pick the one for your shell:
source .venv/Scripts/activate   # Git Bash / WSL on Windows
.venv\Scripts\activate          # Windows cmd.exe
.venv\Scripts\Activate.ps1      # Windows PowerShell
source .venv/bin/activate       # macOS/Linux

pip install -r requirements.txt
python scripts/download_tts_model.py   # one-time, ~330MB
cp .env.example .env          # then fill in whichever API keys you have

fastapi dev app/api/main.py --port 8000
```

Any AI seat whose API key is missing in `.env` automatically falls back to a randomized mock player, so the app runs fine with none, some, or all keys set.

> **Windows:** `fastapi dev`'s console output includes emoji, which crashes on
> the default (non-UTF-8) console codepage. Set `PYTHONUTF8=1` first:
> `export PYTHONUTF8=1` (Git Bash/WSL), `$env:PYTHONUTF8=1` (PowerShell), or
> `set PYTHONUTF8=1` (cmd.exe).

Run tests: `pytest` (from `backend/`, with the venv active).

### Frontend

Uses [Bun](https://bun.sh) instead of npm:

```
cd frontend
bun install
bun run dev
```

Open the printed `localhost` URL. The frontend expects the backend at `http://localhost:8000` by default (override with `VITE_API_BASE`).

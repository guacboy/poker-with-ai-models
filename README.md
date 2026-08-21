# poker-with-ai-models

No-Limit Texas Hold'em against 5 AI opponents (Claude, OpenAI, DeepSeek, Gemini, Grok), each playing through its own API. Python/FastAPI backend (poker engine on [pokerkit](https://github.com/uoftcprg/pokerkit)), React frontend, local text-to-speech for AI trash talk via [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M).

## Tournament format

6-max, 100 BB starting stack, blinds increase every 1 orbit (the button returning to someone who already held it counts as one orbit -- this naturally speeds up as players bust), up to 3 buy-ins per player (human and AI alike, fixed rebuy size), no antes. All of this is tunable in [`backend/app/rules.py`](backend/app/rules.py).

## AI trash talk

Every AI action can carry a short spoken line (synthesized via Kokoro and read aloud), with the prompt pushing for disrespectful, high-ego, no-holding-back trash talk. Whether a given action actually talks depends on how meaningful it is: raising/shoving, a real fold, or calling an actual bet/raise is highly likely (bumped to certain on a turn/river all-in moment); an otherwise-quiet action (a free check, a blind-limp call) still gets a flat 50% shot on every turn (see `talk_chance` in [`backend/app/ai/base.py`](backend/app/ai/base.py)). A hand's winner is separately guaranteed a chance to gloat once the pot's settled, via its own post-hand reaction call -- always on a real showdown, and also on a fold-out win that made it to the turn or river (too early on preflop/flop to be worth bragging about). Symmetrically, an AI that just lost a heads-up pot to the human at showdown on the turn or river is guaranteed a sore-loser reaction of its own (see `_sore_loser_target` in [`backend/app/api/session.py`](backend/app/api/session.py)) -- every real showdown now forces every remaining player to reveal their hand (win or lose), instead of pokerkit's default of letting an outright loser muck without ever showing (see `Hand._force_full_showdown_reveal` in [`backend/app/engine/hand.py`](backend/app/engine/hand.py)).

## Debug Mode

The start screen has a smaller "Debug Mode" button below "Start Tournament". It plays entirely against randomized mock players and never touches any AI provider or API key -- no API usage happens until you actually click "Start Tournament" for a real game. A debug session shows a control widget in the top-right corner:

- **Force All-Ins / Force Call / Force Check / Force Fold** -- pins every AI seat's decision to one action (clamped to whatever's actually legal)
- **Always Show Hands** -- reveals every seat's hole cards regardless of fold/showdown status
- **End Round** -- immediately forfeits the in-progress hand (any chips already in the pot stay forfeited) and deals the next one

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

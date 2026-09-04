# poker-with-ai-models

No-Limit Texas Hold'em against 5 AI opponents (Claude, OpenAI, DeepSeek, Gemini, Grok), each playing through its own API. Python/FastAPI backend with a poker engine built on [pokerkit](https://github.com/uoftcprg/pokerkit), React/TypeScript frontend over WebSockets, local text-to-speech for AI trash talk via [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M).

## What it does

- Five AI seats, each a real call to a different provider (Anthropic, OpenAI, DeepSeek, Google, xAI). All five implement the same `AIPlayer` interface (`backend/app/ai/base.py`), so the game loop and prompt template don't need to know which provider is behind a seat.
- Full poker rules via pokerkit: side pots, hand evaluation, showdown resolution. The engine layer on top (`backend/app/engine/`) handles tournament structure: blind levels, buy-ins/rebuys, elimination, button rotation.
- AI reactions are tied to game state instead of being random. Bots get a guaranteed line when they win a hand, a sore-loser line when they lose a heads-up pot at showdown, and a probability-based chance to talk on other actions depending on how significant the action is.
- Each spoken line is synthesized locally with Kokoro and read aloud with a distinct voice per seat.
- One asyncio task per tournament runs the game loop: dealing, AI turns, the human's turn, showdown, and payouts, each step broadcast as a WebSocket event. The frontend doesn't poll; `useGameSocket` reduces the event stream into UI state.
- AI calls are wrapped in a timeout and fall back to a fold on any error, so a slow or broken provider doesn't freeze or crash the game.
- 100+ pytest tests covering engine correctness and the session/game-loop layer, run in CI on every push along with a frontend build.

## Tech stack

Backend: Python, FastAPI (REST + WebSocket), asyncio, pokerkit, pytest.
AI providers: `anthropic`, `openai` (also used as the client for DeepSeek and xAI/Grok, which use the same API shape), `google-genai`.
Speech: Kokoro-82M (`kokoro-onnx`), local and offline.
Frontend: React 19, TypeScript, Vite, plain WebSocket + `useReducer` (no external state library).
CI: GitHub Actions, runs the backend test suite and a frontend type-check/build on every push.

## Architecture

```
backend/app/
  engine/    pokerkit-backed poker rules: hand.py (one hand), tournament.py (blind
             levels, buy-ins, elimination, button rotation), state.py (serializes
             engine state into per-viewer JSON views)
  ai/        AIPlayer protocol and shared prompt builder (base.py), one module per
             provider (providers/), a randomized mock for debug play
             (mock_player.py), and factory.py to pick real vs. mock per seat
  api/       FastAPI app (main.py), the async game loop and WebSocket broadcast
             layer (session.py), request/response schemas (schemas.py)
  tts/       Kokoro wrapper, run off the event loop via a threadpool
  config.py  env vars, provider model names, per-seat voice map
  rules.py   every tournament rule constant in one place (blinds, buy-ins, etc.)

frontend/src/
  components/  Table, Seat, ActionControls, CommunityCards, SpeechBubble, etc.
  hooks/       useGameSocket (WS connection to a reducer over server events),
               useAudioQueue (plays queued speech clips back to back)
  types/       shared TypeScript types for every WebSocket event shape
```

The game loop is a single asyncio task per tournament (`GameSession._run`). It deals a hand, walks the actor order calling either a real AI provider or awaiting a human action (via a `Future` the REST `/action` endpoint resolves), runs the showdown, and broadcasts each step as a typed WebSocket event.

## Gameplay features

- Pre-action queuing: queue a fold/call/check before it's your turn. It fires as soon as your turn comes up, and options that no longer apply (like "check" after a bet comes in) are hidden.
- Pot-relative bet sizing: buttons for 1/2 pot, pot, 2x pot, and all-in.
- Showdown text: the winning hand's category is shown (including a plain "High card"), a chopped pot is called out, and the community cards that made up the winning hand are highlighted. Only the cards that actually mattered (e.g. the pair itself, not incidental kickers).
- Chip leader tag: an "L" badge marks whoever currently has the most chips among players still in the tournament (no tag at all in a tie, e.g. hand 1 before anyone's won a pot).
- Debug Mode, described below, for testing against mock opponents with no API calls.

## Tournament format

6-max, 100 BB starting stack, blinds increase every 1 orbit (the button returning to someone who already held it counts as one orbit, which naturally speeds up as players bust). Blind levels aren't a fixed schedule -- each level's big blind is computed directly from a growth-factor formula compounding off the starting big blind, so they keep climbing indefinitely no matter how long a tournament (or a heads-up stalemate) runs. Up to 3 buy-ins per player (human and AI alike, fixed rebuy size), no antes. All of this is tunable in [`backend/app/rules.py`](backend/app/rules.py).

## AI trash talk

Every AI action can carry a short spoken line (synthesized via Kokoro and read aloud), with the prompt pushing for disrespectful, high-ego, no-holding-back trash talk. Whether a given action actually talks depends on how meaningful it is: raising/shoving, a real fold, or calling an actual bet/raise always talks; an otherwise-quiet action (a free check, a blind-limp call) still gets a flat 50% shot on every turn instead (see `talk_chance` in [`backend/app/ai/base.py`](backend/app/ai/base.py)).

A hand's winner is separately guaranteed a chance to gloat once the pot's settled, via its own post-hand reaction call: always on a real showdown, and also on a fold-out win that made it to the turn or river (too early on preflop/flop to be worth bragging about). Symmetrically, an AI that just lost a heads-up pot to the human at showdown on the turn or river is guaranteed a sore-loser reaction of its own (see `_sore_loser_target` in [`backend/app/api/session.py`](backend/app/api/session.py)). Every real showdown forces every remaining player to reveal their hand, win or lose, instead of pokerkit's default of letting an outright loser muck without ever showing (see `Hand._force_full_showdown_reveal` in [`backend/app/engine/hand.py`](backend/app/engine/hand.py)).

## Debug Mode

The start screen has a smaller "Debug Mode" button below "Start Tournament". It plays entirely against randomized mock players and never touches any AI provider or API key; no API usage happens until you actually click "Start Tournament" for a real game. A debug session shows a control widget in the top-right corner:

- **Force All-Ins / Force Call / Force Check / Force Fold**: pins every AI seat's decision to one action (clamped to whatever's actually legal)
- **Always Show Hands**: reveals every seat's hole cards regardless of fold/showdown status
- **Force Dialogue**: guarantees every mock AI action, win, and loss comes with a spoken line instead of leaving it to chance
- **End Round**: immediately forfeits the in-progress hand (any chips already in the pot stay forfeited) and deals the next one

## Setup

### Backend

```
cd backend
python -m venv .venv

# activate the venv, pick the one for your shell:
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

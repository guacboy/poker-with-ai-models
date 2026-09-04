import type { SeatViewModel } from "../components/Seat";
import type { PublicPlayer } from "../types/game";

// Purely decorative: what hand #1 always looks like before any tournament
// exists (matches the backend's real starting stack/blinds, but isn't fed by
// a live session) -- used as the dimmed backdrop behind the start button.
const STARTING_STACK = 10_000;
const SMALL_BLIND = 50;
const BIG_BLIND = 100;

// physical seat order: human first, then AI_SEATS order from backend/app/config.py
const SEAT_SPECS: { playerId: string; name: string; kind: "human" | "ai" }[] = [
  { playerId: "human", name: "You", kind: "human" },
  { playerId: "claude", name: "Claude", kind: "ai" },
  { playerId: "openai", name: "OpenAI", kind: "ai" },
  { playerId: "deepseek", name: "DeepSeek", kind: "ai" },
  { playerId: "gemini", name: "Gemini", kind: "ai" },
  { playerId: "grok", name: "Grok", kind: "ai" },
];

export const PLACEHOLDER_BIG_BLIND = BIG_BLIND;
export const PLACEHOLDER_SMALL_BLIND = SMALL_BLIND;
export const PLACEHOLDER_STARTING_STACK = STARTING_STACK;

export const PLACEHOLDER_PLAYERS: PublicPlayer[] = SEAT_SPECS.map((spec) => ({
  player_id: spec.playerId,
  name: spec.name,
  kind: spec.kind,
  stack: STARTING_STACK,
  status: "active",
  buy_ins_used: 1,
  buy_ins_remaining: 2,
}));

export const PLACEHOLDER_SEATS: SeatViewModel[] = SEAT_SPECS.map((spec) => ({
  playerId: spec.playerId,
  name: spec.name,
  kind: spec.kind,
  status: "active",
  stack: STARTING_STACK,
  bet: 0,
  folded: false,
  isButton: false,
  isSmallBlind: false,
  isBigBlind: false,
  isChipLeader: false,
  isToAct: false,
  holeCards: null,
  buyInsUsed: 1,
  buyInsRemaining: 2,
}));

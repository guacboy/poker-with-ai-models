const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// player_id -> filename under assets/png/ (served by the backend at
// /images/<filename>, same pattern as /sounds -- see backend/app/api/main.py).
// "openai"'s file is named gpt.png, everyone else matches their player_id.
const AVATAR_FILE_BY_PLAYER_ID: Record<string, string> = {
  claude: "claude.png",
  openai: "gpt.png",
  deepseek: "deepseek.png",
  gemini: "gemini.png",
  grok: "grok.png",
};

/** The avatar image URL for an AI seat, or null for the human (no bot photo). */
export function avatarUrlFor(playerId: string): string | null {
  const filename = AVATAR_FILE_BY_PLAYER_ID[playerId];
  return filename ? `${API_BASE}/images/${filename}` : null;
}

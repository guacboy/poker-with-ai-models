import type { PublicPlayer } from "../types/game";

interface TournamentStatusProps {
  handCount: number;
  smallBlind: number;
  bigBlind: number;
  handsUntilNextLevel: number;
  players: PublicPlayer[];
  humanPlayerId: string;
}

export function TournamentStatus({
  handCount,
  smallBlind,
  bigBlind,
  handsUntilNextLevel,
  players,
  humanPlayerId,
}: TournamentStatusProps) {
  const human = players.find((p) => p.player_id === humanPlayerId);
  const activeCount = players.filter((p) => p.status === "active").length;

  return (
    <div className="tournament-status">
      <div>
        Hand #{handCount + 1} · Blinds {smallBlind}/{bigBlind}
      </div>
      <div>Next level in {handsUntilNextLevel} hand{handsUntilNextLevel === 1 ? "" : "s"}</div>
      <div>{activeCount} players remaining</div>
      {human && <div>Your buy-ins remaining: {human.buy_ins_remaining}</div>}
    </div>
  );
}

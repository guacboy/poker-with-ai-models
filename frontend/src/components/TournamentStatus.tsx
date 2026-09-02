import type { PublicPlayer } from "../types/game";

interface TournamentStatusProps {
  handCount: number;
  smallBlind: number;
  bigBlind: number;
  handsUntilNextOrbit: number;
  players: PublicPlayer[];
  humanPlayerId: string;
}

export function TournamentStatus({
  handCount,
  smallBlind,
  bigBlind,
  handsUntilNextOrbit,
  players,
  humanPlayerId,
}: TournamentStatusProps) {
  const human = players.find((p) => p.player_id === humanPlayerId);
  const activeCount = players.filter((p) => p.status === "active").length;

  const items = [
    `Hand #${handCount + 1}`,
    `Blinds ${smallBlind}/${bigBlind}`,
    `Next orbit in ${handsUntilNextOrbit} hand${handsUntilNextOrbit === 1 ? "" : "s"}`,
    `${activeCount} players remaining`,
    human ? `Your buy-ins remaining: ${human.buy_ins_remaining}` : null,
  ].filter((item): item is string => item !== null);

  return (
    <div className="tournament-status">
      {items.map((item, i) => (
        <span key={i} className="tournament-status__item">
          {item}
        </span>
      ))}
    </div>
  );
}

import { CommunityCards } from "./CommunityCards";
import { PotDisplay } from "./PotDisplay";
import { Seat, type SeatViewModel } from "./Seat";

const POSITION_CLASSES = [
  "seat-pos-0",
  "seat-pos-1",
  "seat-pos-2",
  "seat-pos-3",
  "seat-pos-4",
  "seat-pos-5",
];

interface TableProps {
  seats: SeatViewModel[]; // fixed table order; index 0 must be the human
  humanPlayerId: string;
  speechMessages: Record<string, string | null>;
  boardCards: string[];
  potTotal: number;
  bigBlind: number;
}

export function Table({
  seats,
  humanPlayerId,
  speechMessages,
  boardCards,
  potTotal,
  bigBlind,
}: TableProps) {
  return (
    <div className="table-felt">
      <div className="table-center">
        <CommunityCards cards={boardCards} />
        <PotDisplay potTotal={potTotal} bigBlind={bigBlind} />
      </div>
      {seats.map((seat, i) => (
        <Seat
          key={seat.playerId}
          seat={seat}
          isHuman={seat.playerId === humanPlayerId}
          speechMessage={speechMessages[seat.playerId] ?? null}
          positionClassName={POSITION_CLASSES[i % POSITION_CLASSES.length]}
          bigBlind={bigBlind}
        />
      ))}
    </div>
  );
}

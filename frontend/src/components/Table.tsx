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
  speechMessages: Record<string, string | null>;
  boardCards: string[];
  potTotal: number;
  bigBlind: number;
  winningHandLabel: string | null;
  // true when the just-finished hand's pot was split across more than one
  // winner (a tie at showdown, or separate main/side pots going to different
  // players) -- combined with winningHandLabel into a single result line
  isChoppedPot: boolean;
  // board cards that made up the winning hand just shown -- see CommunityCards
  winningBoardCards: string[];
}

export function Table({
  seats,
  speechMessages,
  boardCards,
  potTotal,
  bigBlind,
  winningHandLabel,
  isChoppedPot,
  winningBoardCards,
}: TableProps) {
  const resultLabel = isChoppedPot
    ? winningHandLabel
      ? `Split pot -- ${winningHandLabel}`
      : "Split pot"
    : winningHandLabel;
  return (
    <div className="table-felt">
      <div className="table-center">
        <CommunityCards cards={boardCards} winningCards={winningBoardCards} />
        {resultLabel && <div className="winning-hand-label">{resultLabel}</div>}
        <PotDisplay potTotal={potTotal} bigBlind={bigBlind} />
      </div>
      {seats.map((seat, i) => (
        <Seat
          key={seat.playerId}
          seat={seat}
          speechMessage={speechMessages[seat.playerId] ?? null}
          positionClassName={POSITION_CLASSES[i % POSITION_CLASSES.length]}
          bigBlind={bigBlind}
        />
      ))}
    </div>
  );
}

import { PlayingCard } from "./PlayingCard";
import { SpeechBubble } from "./SpeechBubble";
import type { PlayerKind, PlayerStatus } from "../types/game";
import { formatBB } from "../utils/formatChips";

export interface SeatViewModel {
  playerId: string;
  name: string;
  kind: PlayerKind;
  status: PlayerStatus;
  stack: number;
  bet: number;
  folded: boolean;
  isButton: boolean;
  isSmallBlind: boolean;
  isBigBlind: boolean;
  isToAct: boolean;
  holeCards: string[] | null;
  buyInsUsed: number;
  buyInsRemaining: number;
  lastActionLabel?: string;
}

interface SeatProps {
  seat: SeatViewModel;
  isHuman: boolean;
  speechMessage: string | null;
  positionClassName: string;
  bigBlind: number;
}

export function Seat({ seat, isHuman, speechMessage, positionClassName, bigBlind }: SeatProps) {
  const classes = [
    "seat",
    positionClassName,
    seat.isToAct ? "seat--acting" : "",
    seat.folded ? "seat--folded" : "",
    seat.status === "eliminated" ? "seat--eliminated" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      {speechMessage && <SpeechBubble message={speechMessage} />}
      <div className="seat__cards">
        <PlayingCard card={seat.holeCards?.[0]} hidden={!seat.holeCards} />
        <PlayingCard card={seat.holeCards?.[1]} hidden={!seat.holeCards} />
      </div>
      <div className="seat__info">
        <div className="seat__name">
          {seat.name}
          {isHuman && <span className="seat__you-tag">you</span>}
        </div>
        {seat.lastActionLabel && <div className="seat__last-action">{seat.lastActionLabel}</div>}
        <div className="seat__stack">{formatBB(seat.stack, bigBlind)}</div>
        <div className="seat__badges">
          {seat.isButton && <span className="badge badge--button">D</span>}
          {seat.isSmallBlind && <span className="badge badge--blind">SB</span>}
          {seat.isBigBlind && <span className="badge badge--blind">BB</span>}
          {seat.buyInsUsed > 1 && (
            <span className="badge badge--rebuy">rebuy {seat.buyInsUsed - 1}</span>
          )}
        </div>
        {seat.status === "eliminated" && <div className="seat__eliminated-tag">Eliminated</div>}
      </div>
      {seat.bet > 0 && <div className="seat__bet-chip">{formatBB(seat.bet, bigBlind)}</div>}
    </div>
  );
}

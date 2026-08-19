import { formatBB } from "../utils/formatChips";

interface PotDisplayProps {
  potTotal: number;
  bigBlind: number;
}

export function PotDisplay({ potTotal, bigBlind }: PotDisplayProps) {
  if (potTotal <= 0) return null;
  return <div className="pot-display">Pot: {formatBB(potTotal, bigBlind)}</div>;
}

const SUIT_SYMBOL: Record<string, string> = { s: "♠", h: "♥", d: "♦", c: "♣" };
const RED_SUITS = new Set(["h", "d"]);

interface PlayingCardProps {
  card?: string; // e.g. "Th", "Ad" -- rank then suit
  hidden?: boolean; // opponent's hole card, unknown to the viewer
  empty?: boolean; // board slot not dealt yet
  // this card was part of the winning hand just shown down -- nudged upward
  // to call it out, e.g. the 4 board cards that make a straight
  highlighted?: boolean;
}

export function PlayingCard({ card, hidden, empty, highlighted }: PlayingCardProps) {
  if (empty) {
    return <div className="playing-card playing-card--empty" />;
  }
  if (hidden || !card) {
    return <div className="playing-card playing-card--back" />;
  }
  const rank = card.slice(0, -1);
  const suit = card.slice(-1).toLowerCase();
  const isRed = RED_SUITS.has(suit);
  return (
    <div
      className={`playing-card ${isRed ? "playing-card--red" : "playing-card--black"}${highlighted ? " playing-card--highlighted" : ""}`}
    >
      <span className="playing-card__rank">{rank}</span>
      <span className="playing-card__suit">{SUIT_SYMBOL[suit] ?? suit}</span>
    </div>
  );
}

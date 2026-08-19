import { PlayingCard } from "./PlayingCard";

interface CommunityCardsProps {
  cards: string[];
}

export function CommunityCards({ cards }: CommunityCardsProps) {
  const slots = Array.from({ length: 5 }, (_, i) => cards[i]);
  return (
    <div className="community-cards">
      {slots.map((card, i) => (
        <PlayingCard key={i} card={card} empty={!card} />
      ))}
    </div>
  );
}

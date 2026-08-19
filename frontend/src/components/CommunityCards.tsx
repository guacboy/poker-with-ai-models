import { PlayingCard } from "./PlayingCard";

interface CommunityCardsProps {
  cards: string[];
}

export function CommunityCards({ cards }: CommunityCardsProps) {
  const slots = Array.from({ length: 5 }, (_, i) => cards[i]);
  return (
    <div className="community-cards">
      {slots.map((card, i) => (
        // keying on the card (not just the slot index) forces a remount the
        // moment a slot goes from empty to dealt, which is what replays the
        // reveal animation -- without it React just patches the same node in
        // place and the card would pop in with no transition
        <PlayingCard key={`${i}-${card ?? "empty"}`} card={card} empty={!card} />
      ))}
    </div>
  );
}

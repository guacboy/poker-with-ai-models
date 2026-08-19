interface PotDisplayProps {
  potTotal: number;
}

export function PotDisplay({ potTotal }: PotDisplayProps) {
  if (potTotal <= 0) return null;
  return (
    <div className="pot-display">
      Pot: {potTotal.toLocaleString()}
    </div>
  );
}

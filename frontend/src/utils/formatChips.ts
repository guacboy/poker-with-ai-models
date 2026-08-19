export function formatBB(amount: number, bigBlind: number): string {
  if (bigBlind <= 0) return `${amount}`;
  const rounded = Math.round((amount / bigBlind) * 10) / 10;
  const text = Number.isInteger(rounded) ? `${rounded}` : rounded.toFixed(1);
  return `${text}BB`;
}

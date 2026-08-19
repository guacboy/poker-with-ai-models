export function chipsToBB(chips: number, bigBlind: number): number {
  if (bigBlind <= 0) return chips;
  return Math.round((chips / bigBlind) * 10) / 10;
}

export function bbToChips(bb: number, bigBlind: number): number {
  return Math.round(bb * bigBlind);
}

export function formatBB(amount: number, bigBlind: number): string {
  if (bigBlind <= 0) return `${amount}`;
  const rounded = chipsToBB(amount, bigBlind);
  const text = Number.isInteger(rounded) ? `${rounded}` : rounded.toFixed(1);
  return `${text}BB`;
}

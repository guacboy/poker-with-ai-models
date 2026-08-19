import { useEffect, useRef } from "react";
import type { LogEntry } from "../types/game";

interface HandHistoryLogProps {
  entries: LogEntry[];
}

export function HandHistoryLog({ entries }: HandHistoryLogProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [entries.length]);

  return (
    <div className="hand-history-log">
      {entries.map((entry) => (
        <div key={entry.id} className="hand-history-log__entry">
          {entry.text}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

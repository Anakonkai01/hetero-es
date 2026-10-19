import { useEffect,useState } from "react";

/** The current time in ms, refreshed every `everyMs`, so a component can show "5 min ago" without reading the clock while rendering. */
export function useNow(everyMs = 30000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), everyMs); return () => clearInterval(timer); }, [everyMs]);
  return now;
}

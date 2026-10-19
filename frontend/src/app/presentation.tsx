import { useCallback,useEffect,useMemo,useState,type ReactNode } from "react";
import { PresentationContext } from "./presentationContext";

const KEY = "heteroes.present";

const initial = () => {
  try { return new URLSearchParams(location.search).get("present") === "1" || sessionStorage.getItem(KEY) === "1"; } catch { return false; }
};

/** Presentation mode: larger text, technical identifiers hidden, scene shortcuts. Per browser tab, never stored on the server. */
export function PresentationProvider({ children }: { children: ReactNode }) {
  const [on, setOn] = useState(initial);
  useEffect(() => {
    document.documentElement.dataset.present = on ? "1" : "";
    try { sessionStorage.setItem(KEY, on ? "1" : "0"); } catch { /* blocked storage: the mode lasts until reload */ }
  }, [on]);
  const set = useCallback((value: boolean) => setOn(value), []);
  const toggle = useCallback(() => setOn(value => !value), []);
  const value = useMemo(() => ({ on, set, toggle }), [on, set, toggle]);
  return <PresentationContext.Provider value={value}>{children}</PresentationContext.Provider>;
}

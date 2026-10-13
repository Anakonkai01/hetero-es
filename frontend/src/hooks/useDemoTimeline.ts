import { useQuery } from "@tanstack/react-query";
import type { Timeline } from "../lib/runFrame";

/** The real finished run shipped with the website (see scripts/export-demo-run.py). */
export function useDemoTimeline() {
  return useQuery({
    queryKey: ["demo-run"], retry: false, staleTime: Infinity,
    queryFn: async () => {
      const reply = await fetch("/demo/run.json");
      if (!reply.ok) throw new Error("DEMO_UNAVAILABLE");
      return reply.json() as Promise<Timeline>;
    },
  });
}

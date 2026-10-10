import { useScopeKey } from "../app/session";
import { useQuery } from "@tanstack/react-query";

import { getExperiments } from "../api/experiments";

/** Polled so that coordinator confirmations (start, cancel) show up without a manual refresh. */
export const EXPERIMENT_POLL_MS = 2500;

export function useExperiments() {
  const scope = useScopeKey();
  return useQuery({
    enabled: scope.every(Boolean),
    queryKey: ["experiments", ...scope],
    queryFn: getExperiments,
    refetchInterval: EXPERIMENT_POLL_MS,
  });
}

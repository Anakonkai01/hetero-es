import { useQuery } from "@tanstack/react-query";
import { useScopeKey } from "../app/session";

import { getCandidate } from "../api/candidates";

export function useCandidate(candidateId: string) {
  const scope = useScopeKey();
  return useQuery({
    queryKey: ["candidate", candidateId, ...scope],
    queryFn: () => getCandidate(candidateId),
    enabled: scope.every(Boolean) && Boolean(candidateId),
  });
}

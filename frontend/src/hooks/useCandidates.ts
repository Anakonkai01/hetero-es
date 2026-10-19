import { useQuery } from "@tanstack/react-query";
import { useScopeKey } from "../app/session";

import { getCandidates } from "../api/candidates";

export function useCandidates(generationId: string | undefined) {
  const scope = useScopeKey();
  return useQuery({
    refetchInterval: 2500,
    queryKey: ["candidates", generationId, ...scope],
    queryFn: () => getCandidates(generationId!),
    enabled: scope.every(Boolean) && Boolean(generationId),
  });
}

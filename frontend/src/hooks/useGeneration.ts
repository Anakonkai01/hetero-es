import { useScopeKey } from "../app/session";
import { useQuery } from "@tanstack/react-query";

import { getGeneration } from "../api/generations";

export function useGeneration(
  experimentId: string,
  generationId: string | undefined,
) {
  const scope = useScopeKey();
  return useQuery({
    queryKey: ["generation", experimentId, generationId, ...scope],
    queryFn: () => getGeneration(experimentId, generationId!),
    enabled: scope.every(Boolean) && Boolean(experimentId && generationId),
  });
}

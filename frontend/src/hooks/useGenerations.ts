import { useQuery } from "@tanstack/react-query";
import { useScopeKey } from "../app/session";

import { getGenerations } from "../api/generations";

export function useGenerations(experimentId: string | undefined) {
  const scope = useScopeKey();
  return useQuery({
    refetchInterval: 2500,
    queryKey: ["generations", experimentId, ...scope],
    queryFn: () => getGenerations(experimentId!),
    enabled: scope.every(Boolean) && Boolean(experimentId),
  });
}

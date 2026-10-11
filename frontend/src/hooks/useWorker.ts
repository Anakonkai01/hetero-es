import { useScopeKey } from "../app/session";
import { useQuery } from "@tanstack/react-query";

import { getWorker } from "../api/workers";

export function useWorker(workerId: string) {
  const scope = useScopeKey();
  return useQuery({
    refetchInterval:3000,
    queryKey: ["worker", workerId, ...scope],
    queryFn: () => getWorker(workerId),
    enabled: scope.every(Boolean) && Boolean(workerId),
  });
}

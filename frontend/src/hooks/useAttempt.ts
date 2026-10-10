import { useScopeKey } from "../app/session";
import { useQuery } from "@tanstack/react-query";

import { getAttempt } from "../api/attempts";

export function useAttempt(attemptId: string | undefined) {
  const scope = useScopeKey();
  return useQuery({
    queryKey: ["attempt", attemptId, ...scope],
    queryFn: () => getAttempt(attemptId!),
    enabled: scope.every(Boolean) && Boolean(attemptId),
  });
}

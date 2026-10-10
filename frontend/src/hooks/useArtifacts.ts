import { useScopeKey } from "../app/session";
import { useQuery } from "@tanstack/react-query";

import { getArtifacts } from "../api/artifacts";

export function useArtifacts() {
  const scope = useScopeKey();
  return useQuery({
    enabled: scope.every(Boolean),
    queryKey: ["artifacts", ...scope],
    queryFn: getArtifacts,
  });
}

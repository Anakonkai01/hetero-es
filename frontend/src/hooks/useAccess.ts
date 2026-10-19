import { useMutation,useQuery,useQueryClient } from "@tanstack/react-query";
import * as api from "../api/access";
import { useScopeKey } from "../app/session";

export function useResources() {
  const scope = useScopeKey();
  return useQuery({ queryKey: ["resources", ...scope], queryFn: api.getResourceOverview, enabled: scope.every(Boolean), refetchInterval: 2500 });
}
export function useModels() {
  const scope = useScopeKey();
  return useQuery({ queryKey: ["models", ...scope], queryFn: api.getModels, enabled: scope.every(Boolean) });
}
export function useAudit() {
  const scope = useScopeKey();
  return useQuery({ queryKey: ["audit", ...scope], queryFn: api.getAudit, enabled: scope.every(Boolean), refetchInterval: 2500 });
}


export function useAccessMutation<T, R>(mutationFn: (input: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn, onSuccess: () => queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "session" }) });
}

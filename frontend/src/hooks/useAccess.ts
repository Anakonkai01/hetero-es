import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/access";
import { useScopeKey, useSession } from "../app/session";

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
export function useRegistry() {
  const scope = useScopeKey();
  const { workspace } = useSession();
  return useQuery({ queryKey: ["registry", ...scope], queryFn: api.getWorkerRegistry, enabled: scope.every(Boolean) && workspace?.role === "ADMIN" });
}

export function useAccessMutation<T, R>(mutationFn: (input: T) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn, onSuccess: () => queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "session" }) });
}

export function useMyWorkers() {
  const { session } = useSession();
  return useQuery({ queryKey: ["my-workers", session?.user.userId], queryFn: api.getMyWorkers, enabled: Boolean(session), refetchInterval: 2500 });
}
export function useDatasets() {
  const scope = useScopeKey();
  return useQuery({ queryKey: ["datasets", ...scope], queryFn: api.getDatasets, enabled: scope.every(Boolean) });
}

export function useMyResourceSubmissions() {
  const { session } = useSession();
  return useQuery({ queryKey: ["resource-submissions", session?.user.userId], queryFn: api.getMyResourceSubmissions, enabled: Boolean(session), refetchInterval: 2500 });
}
export function useMyInvitations() {
  const { session } = useSession();
  return useQuery({ queryKey: ["invitations", session?.user.userId], queryFn: api.getMyInvitations, enabled: Boolean(session), refetchInterval: 2500 });
}

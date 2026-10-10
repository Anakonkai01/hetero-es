import { useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getSession, login, logout } from "../api/access";
import { ApiError, setActiveWorkspace, setDemoToken } from "../api/client";
import { SessionContext } from "./session";

const WORKSPACE_KEY = "heteroes.demo-workspace";

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [workspaceId, setWorkspaceId] = useState(sessionStorage.getItem(WORKSPACE_KEY) ?? "");
  const query = useQuery({
    queryKey: ["session"],
    queryFn: async () => {
      const session = await getSession();
      const selected = sessionStorage.getItem(WORKSPACE_KEY);
      setActiveWorkspace(session.workspaces.find((item) => item.workspaceId === selected)?.workspaceId ?? session.workspaces[0]?.workspaceId ?? "");
      return session;
    },
    retry: false,
    refetchInterval: 15000,
  });
  const session = query.error instanceof ApiError && query.error.status === 401 ? undefined : query.data;
  const workspace = session?.workspaces.find((item) => item.workspaceId === workspaceId) ?? session?.workspaces[0];

  async function selectWorkspace(id: string) {
    if (!session?.workspaces.some((item) => item.workspaceId === id)) return;
    await queryClient.cancelQueries({ predicate: (query) => query.queryKey[0] !== "session" });
    setActiveWorkspace(id);
    sessionStorage.setItem(WORKSPACE_KEY, id);
    setWorkspaceId(id);
    // Dispose scoped data rather than carrying another workspace's stale data forward.
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
  }

  async function signIn(input: { username: string; password: string }) {
    const result = await login(input);
    await queryClient.cancelQueries();
    queryClient.clear();
    setDemoToken(result.demoToken);
    const id = result.workspaces[0]?.workspaceId ?? "";
    setActiveWorkspace(id);
    sessionStorage.setItem(WORKSPACE_KEY, id);
    setWorkspaceId(id);
    queryClient.setQueryData(["session"], { user: result.user, workspaces: result.workspaces });
  }

  async function signOut() {
    // Preserve the session if the server cannot confirm revocation.
    await logout();
    await queryClient.cancelQueries();
    setDemoToken("");
    setActiveWorkspace("");
    sessionStorage.removeItem(WORKSPACE_KEY);
    setWorkspaceId("");
    queryClient.clear();
    queryClient.setQueryData(["session"], null);
  }

  async function refreshSession() { await query.refetch(); }

  return <SessionContext.Provider value={{
    session: session ?? undefined,
    workspace,
    pending: query.isPending,
    unavailable: query.isError && !(query.error instanceof ApiError && query.error.status === 401),
    selectWorkspace: (id) => { void selectWorkspace(id); },
    signIn, signOut, refreshSession,
  }}>{children}</SessionContext.Provider>;
}

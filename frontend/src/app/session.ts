import { createContext, useContext } from "react";
import type { Session, Workspace } from "../types/access";

export interface SessionState {
  session?: Session;
  workspace?: Workspace;
  pending: boolean;
  unavailable: boolean;
  selectWorkspace: (workspaceId: string) => void;
  signIn: (input: { username: string; password: string }) => Promise<void>;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

export const SessionContext = createContext<SessionState | null>(null);
export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession requires SessionProvider");
  return value;
}

export function useScopeKey() {
  const { session, workspace } = useSession();
  return [session?.user.userId, workspace?.workspaceId];
}

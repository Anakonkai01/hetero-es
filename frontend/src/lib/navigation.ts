import { useLocation } from "react-router";

/** Router state that lets a detail page offer a "back" button to where the user came from. */
export interface BackState {
  backTo: string;
  backLabel: string;
}

export const fromDashboard: BackState = {
  backTo: "/dashboard",
  backLabel: "Dashboard",
};

export const fromEvents: BackState = {
  backTo: "/events",
  backLabel: "Events",
};

export const fromArtifacts: BackState = {
  backTo: "/artifacts",
  backLabel: "Artifacts",
};

export function useBackState(): BackState | undefined {
  const state = useLocation().state as Partial<BackState> | null;

  return state?.backTo && state.backLabel
    ? { backTo: state.backTo, backLabel: state.backLabel }
    : undefined;
}

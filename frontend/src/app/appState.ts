import { createContext, useContext } from "react";
import type { Scenario } from "../mocks/scenario";

export interface AppState {
  /** Demo scenario chosen in the "Simulate state" selector. */
  scenario: Scenario;
  setScenario: (scenario: Scenario) => void;

  toast: string;
  flash: (message: string) => void;

  refreshing: boolean;
  refresh: () => void;
  /** Resets a failed region (simulated by going back to the normal scenario). */
  retryRegion: () => void;

  /** Timestamp of the last successful data update. */
  lastUpdated: number;
}

export const AppStateContext = createContext<AppState | null>(null);

export function useAppState(): AppState {
  const value = useContext(AppStateContext);

  if (!value) {
    throw new Error("useAppState must be used inside AppStateProvider");
  }

  return value;
}

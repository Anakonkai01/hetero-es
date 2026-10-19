import { createContext, useContext } from 'react';

export interface AppState {
  toast: string;
  flash: (message: string) => void;

  refreshing: boolean;
  refresh: () => void;
  /** Refreshes a failed region. */
  retryRegion: () => void;

  /** Timestamp of the last successful data update. */
  lastUpdated: number;
}

export const AppStateContext = createContext<AppState | null>(null);

export function useAppState(): AppState {
  const value = useContext(AppStateContext);

  if (!value) {
    throw new Error('useAppState must be used inside AppStateProvider');
  }

  return value;
}

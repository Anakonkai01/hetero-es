import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppStateContext, type AppState } from './appState';

const TOAST_MS = 2600;
const MIN_REFRESH_MS = 800;

export function AppStateProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [toast, setToast] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(() => Date.now());
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(
    () =>
      queryClient.getQueryCache().subscribe((event) => {
        if (event.type === 'updated' && event.action.type === 'success') {
          setLastUpdated(event.query.state.dataUpdatedAt);
        }
      }),
    [queryClient],
  );

  const flash = useCallback((message: string) => {
    setToast(message);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), TOAST_MS);
  }, []);

  const refresh = useCallback(() => {
    if (refreshing) return;
    setRefreshing(true);
    const minimumDuration = new Promise((resolve) => setTimeout(resolve, MIN_REFRESH_MS));
    void Promise.all([queryClient.invalidateQueries(), minimumDuration]).then(() => setRefreshing(false));
  }, [queryClient, refreshing]);

  const retryRegion = useCallback(() => {
    void queryClient.invalidateQueries();
    flash('Refreshing runtime data');
  }, [flash, queryClient]);

  const value = useMemo<AppState>(
    () => ({ toast, flash, refreshing, refresh, retryRegion, lastUpdated }),
    [toast, flash, refreshing, refresh, retryRegion, lastUpdated],
  );
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

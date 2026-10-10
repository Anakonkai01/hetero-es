import { useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { setScenario as setMockScenario } from "../mocks/scenario";
import type { Scenario } from "../mocks/scenario";
import { AppStateContext, type AppState } from "./appState";

const TOAST_MS = 2600;
const MIN_REFRESH_MS = 800;

export function AppStateProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const [scenario, setScenarioState] = useState<Scenario>("normal");
  const [toast, setToast] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(() => Date.now());

  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const scenarioRef = useRef(scenario);

  useEffect(() => {
    scenarioRef.current = scenario;
  }, [scenario]);

  // The "last updated" time follows the newest successful query result.
  useEffect(() => {
    return queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "success") {
        setLastUpdated(event.query.state.dataUpdatedAt);
      }
    });
  }, [queryClient]);

  const flash = useCallback((message: string) => {
    setToast(message);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), TOAST_MS);
  }, []);

  const setScenario = useCallback(
    (next: Scenario) => {
      setMockScenario(next);
      setScenarioState(next);
      void queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const refresh = useCallback(() => {
    if (refreshing) {
      return;
    }

    setRefreshing(true);

    const minimumDuration = new Promise((resolve) =>
      setTimeout(resolve, MIN_REFRESH_MS),
    );

    void Promise.all([queryClient.invalidateQueries(), minimumDuration]).then(
      () => {
        setRefreshing(false);

        if (scenarioRef.current === "stale") {
          flash("Could not reconnect. Keeping the stale data.");
        }
      },
    );
  }, [flash, queryClient, refreshing]);

  const retryRegion = useCallback(() => {
    setScenario("normal");
    flash("Region reloaded (simulated)");
  }, [flash, setScenario]);

  const value = useMemo<AppState>(
    () => ({
      scenario,
      setScenario,
      toast,
      flash,
      refreshing,
      refresh,
      retryRegion,
      lastUpdated,
    }),
    [
      scenario,
      setScenario,
      toast,
      flash,
      refreshing,
      refresh,
      retryRegion,
      lastUpdated,
    ],
  );

  return (
    <AppStateContext.Provider value={value}>
      {children}
    </AppStateContext.Provider>
  );
}

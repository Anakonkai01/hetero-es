import { useScopeKey } from "../app/session";
import { useQuery } from "@tanstack/react-query";

import { getEvents } from "../api/events";

export function useEvents() {
  const scope = useScopeKey();
  return useQuery({
    enabled: scope.every(Boolean),
    queryKey: ["events", ...scope],
    queryFn: getEvents,
  });
}

import { useQuery } from '@tanstack/react-query';
import { useScopeKey } from '../app/session';

import { getEvents } from '../api/events';

export function useEvents() {
  const scope = useScopeKey();
  return useQuery({
    enabled: scope.every(Boolean),
    queryKey: ['events', ...scope],
    queryFn: getEvents,
  });
}

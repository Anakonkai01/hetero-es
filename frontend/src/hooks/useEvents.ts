import { useQuery } from '@tanstack/react-query';
import { useScopeKey } from '../app/session';

import { getEvents } from '../api/events';

export function useEvents(experimentId?: string) {
  const scope = useScopeKey();
  return useQuery({
    enabled: scope.every(Boolean),
    queryKey: ['events', ...scope, experimentId ?? 'all'],
    queryFn: () => getEvents(experimentId),
  });
}

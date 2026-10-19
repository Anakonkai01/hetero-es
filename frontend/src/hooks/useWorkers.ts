import { useQuery } from '@tanstack/react-query';
import { useScopeKey } from '../app/session';

import { getWorkers } from '../api/workers';

export function useWorkers() {
  const scope = useScopeKey();
  return useQuery({
    refetchInterval: 2500,
    enabled: scope.every(Boolean),
    queryKey: ['workers', ...scope],
    queryFn: getWorkers,
  });
}

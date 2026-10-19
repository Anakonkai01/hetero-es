import { useQuery } from '@tanstack/react-query';
import { useScopeKey } from '../app/session';

import { getExperiment } from '../api/experiments';
import { EXPERIMENT_POLL_MS } from './useExperiments';

export function useExperiment(experimentId: string) {
  const scope = useScopeKey();
  return useQuery({
    queryKey: ['experiment', experimentId, ...scope],
    queryFn: () => getExperiment(experimentId),
    enabled: scope.every(Boolean) && Boolean(experimentId),
    refetchInterval: EXPERIMENT_POLL_MS,
  });
}

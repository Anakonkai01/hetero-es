import { useMutation,useQueryClient } from "@tanstack/react-query";
import { useScopeKey } from "../app/session";

import {
createExperiment,
requestExperimentCancel,
} from "../api/experiments";

export function useCreateExperiment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createExperiment,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["experiments"] }),
  });
}

export function useRequestCancel() {
  const queryClient = useQueryClient();
  const scope = useScopeKey();

  return useMutation({
    mutationFn: requestExperimentCancel,
    onSuccess: (experiment) => {
      queryClient.setQueryData(
        ["experiment", experiment.experimentId, ...scope],
        experiment,
      );
      return queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
  });
}

import { useEffect,useRef } from "react";
import { useAppState } from "../../app/appState";
import { useExperiments } from "../../hooks/useExperiments";
import type { ExperimentStatus } from "../../types/experiment";
/** Announces coordinator confirmations (start and cancel) as toasts, on any page. */
export function useStatusToasts() {
    const { flash } = useAppState();
    const { data: experiments } = useExperiments();
    const previous = useRef(new Map<string, ExperimentStatus>());
    useEffect(() => {
        if (!experiments) {
            return;
        }
        const seen = previous.current;
        for (const experiment of experiments) {
            const before = seen.get(experiment.experimentId);
            if (before && before !== "RUNNING" && experiment.status === "RUNNING") {
                flash(`Coordinator confirmed: the experiment is running${""}`);
            }
            if (before && before !== "CANCELLED" && experiment.status === "CANCELLED") {
                flash(`Coordinator confirmed: CANCELLED${""}`);
            }
            seen.set(experiment.experimentId, experiment.status);
        }
    }, [experiments, flash]);
}

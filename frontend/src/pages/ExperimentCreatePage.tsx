import { useNavigate } from "react-router";
import { useCreateExperiment } from "../hooks/useExperimentMutations";
import { ExperimentConfiguration } from "../components/experiments/ExperimentConfiguration";
import { PageHeader } from "../components/ui/PageHeader";
import { IS_MOCK } from "../lib/dataSource";
export function ExperimentCreatePage() {
  const create = useCreateExperiment(); const navigate = useNavigate();
  return <><PageHeader title="Create experiment" description={IS_MOCK ? "Choose a model reference, dataset splits, ES configuration and your allocated Workers." : "Choose a built-in workload, ES configuration and workers from the shared pool."} />
    <section className="card"><ExperimentConfiguration pending={create.isPending} onSave={async (configuration) => { const e = await create.mutateAsync(configuration); navigate(`/experiments/${e.experimentId}`); }} /></section>
  </>;
}

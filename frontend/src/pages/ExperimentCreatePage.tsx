import { useNavigate } from "react-router";
import { useCreateExperiment } from "../hooks/useExperimentMutations";
import { ExperimentConfiguration } from "../components/experiments/ExperimentConfiguration";
import { PageHeader } from "../components/ui/PageHeader";
export function ExperimentCreatePage() {
  const create = useCreateExperiment(); const navigate = useNavigate();
  return <><PageHeader title="Create experiment" description="Choose a model reference, dataset splits, ES configuration and your allocated Workers." />
    <section className="card"><ExperimentConfiguration pending={create.isPending} onSave={async (configuration) => { const e = await create.mutateAsync(configuration); navigate(`/experiments/${e.experimentId}`); }} /></section>
  </>;
}

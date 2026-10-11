import {useProduct} from '@heteroes/product-ui';
import { useNavigate } from "react-router";
import { useCreateExperiment } from "../hooks/useExperimentMutations";
import { ExperimentConfiguration } from "../components/experiments/ExperimentConfiguration";
import { PageHeader } from "../components/ui/PageHeader";
import { IS_MOCK } from "../lib/dataSource";
export function ExperimentCreatePage() {
  const {t}=useProduct();
  const create = useCreateExperiment(); const navigate = useNavigate();
  return <><PageHeader title={t("Create experiment")} description={IS_MOCK ? t("Choose a model reference, dataset splits, ES configuration and your allocated Workers.") : t("Choose a built-in workload, ES configuration and workers from the shared pool.")} />
    <section className="card"><ExperimentConfiguration pending={create.isPending} onSave={async (configuration) => { const e = await create.mutateAsync(configuration); navigate(`/experiments/${e.experimentId}`); }} /></section>
  </>;
}

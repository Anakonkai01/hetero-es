import {useProduct} from '@heteroes/product-ui';
import { Link } from "react-router";
import { QueryState } from "../components/common/QueryState";
import { PageHeader } from "../components/ui/PageHeader";
import { Badge } from "../components/ui/Badge";
import { EXPERIMENT_STATUS } from "../lib/labels";
import { useExperiments } from "../hooks/useExperiments";
import { useWorkers } from "../hooks/useWorkers";

export function SchedulingPage() {
  const {t}=useProduct();
  const experiments = useExperiments();
  const workers = useWorkers();
  return <>
    <PageHeader title={t("Worker usage & scheduling")} description={t("Inspect the permitted worker set and runtime state for each experiment you can access.")} />
    <div className="note">{t("Participants select permitted workers and a scheduling policy. The real Coordinator owns connectivity, admission, candidate/attempt assignment, retries and leases. This page does not establish network connections.")}</div>
    <QueryState isPending={experiments.isPending || workers.isPending} isError={experiments.isError || workers.isError} hasData={Boolean(experiments.data && workers.data)} title={t("Could not load worker usage")}>
      <section className="card"><div className="ch"><h2>{t("Experiment → Worker set")}</h2></div><div className="cb demo-form">
        {!experiments.data?.length && <p className="hint">{t("No experiments in your current scope.")}</p>}
        {experiments.data?.map((experiment) => <div className="demo-item" key={experiment.experimentId}><div><Link className="link" to={`/experiments/${experiment.experimentId}`}>{experiment.name}</Link><div className="hint">{experiment.schedulerPolicy} · {experiment.syncMode}</div><div className="hint">{(experiment.workerIds ?? []).map((id) => `${id} (${workers.data?.find((worker) => worker.workerId === id)?.status ?? "outside current pool"})`).join(", ")}</div></div><Badge info={EXPERIMENT_STATUS[experiment.status]} /></div>)}
      </div></section>
    </QueryState>
  </>;
}

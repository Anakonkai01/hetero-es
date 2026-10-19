import { useProduct } from '@heteroes/product-ui';
import { Link } from "react-router";
import { useGeneration } from "../../hooks/useGeneration";
import { shortId } from "../../lib/format";
import type { Experiment } from "../../types/experiment";
import { ProgressBar } from "../ui/ProgressBar";
interface CurrentGenerationProgressProps {
    experiment: Experiment;
    linkGeneration?: boolean;
}
export function CurrentGenerationProgress({ experiment, linkGeneration, }: CurrentGenerationProgressProps) {
    const { t } = useProduct();
    const generationId = experiment.maxGenerations ? undefined : experiment.currentGenerationId;
    const { data: generation } = useGeneration(experiment.experimentId, generationId);
    if (experiment.maxGenerations)
        return <div className="prog"><span>{experiment.completedGenerations ?? 0}/{experiment.maxGenerations} {t("generations completed")}{["RUNNING", "PAUSING"].includes(experiment.status) ? ` · ${(experiment.committedCandidateCount) ?? 0}/${experiment.candidatesPerGeneration} ${t('Candidates in current generation')}` : ""}</span><ProgressBar done={experiment.completedGenerations ?? 0} total={experiment.maxGenerations}/></div>;
    if (!generationId) {
        return <span className="mut">{t("No running generation")}</span>;
    }
    if (!generation) {
        return <span className="mut">{t("Loading…")}</span>;
    }
    const short = shortId(generation.generationId);
    return (<div className="prog">
      <span>
        {linkGeneration ? (<Link className="link mono" to={`/experiments/${experiment.experimentId}/generations/${generation.generationId}`}>
            {short}
          </Link>) : (<span className="mono">{short}</span>)}{" "}
        · {generation.committedCandidateCount} / {generation.candidateCount}{" "}
        {t("committed")}</span>
      <ProgressBar done={generation.committedCandidateCount} total={generation.candidateCount}/>
    </div>);
}

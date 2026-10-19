import { useProduct } from '@heteroes/product-ui';
import { Link } from 'react-router';
import { formatDateTime } from '../../lib/format';
import { EXPERIMENT_STATUS } from '../../lib/labels';
import type { Experiment } from '../../types/experiment';
import { Badge } from '../ui/Badge';
import { ProgressBar } from '../ui/ProgressBar';
export function RunCard({experiment:e}:{experiment:Experiment}){
 const {t}=useProduct();const done=e.completedGenerations??0;
 return <article className="run-card"><div className="run-card-top"><h2><Link to={`/experiments/${e.experimentId}`}>{e.name}</Link></h2><Badge info={EXPERIMENT_STATUS[e.status]}/></div><p className="run-model">{e.modelName} · {e.task}</p><div className="run-progress"><span>{t('Generation progress')}</span><b>{done} / {e.maxGenerations??'—'}</b></div><ProgressBar done={done} total={e.maxGenerations??0}/><dl className="run-meta"><div><dt>{t('Candidates / generation')}</dt><dd>{e.candidatesPerGeneration}</dd></div><div><dt>{t('Workers')}</dt><dd>{e.workerIds?.length??'—'}</dd></div><div><dt>{t('Seed strategy')}</dt><dd className="mono">{e.baseSeed??t('Per candidate')}</dd></div></dl>{e.waitingReason&&<p className="waiting">{e.waitingReason}</p>}<footer><small>{formatDateTime(e.createdAt)}</small><Link className="link" to={`/experiments/${e.experimentId}`}>{t(e.status==='DRAFT'?'Open / edit draft':'Open experiment')} →</Link></footer></article>;
}

import {useState} from 'react';
import {Link} from 'react-router';
import {useQuery} from '@tanstack/react-query';
import {useProduct,Status,useObservationTime,fleetResources} from '@heteroes/product-ui';
import {useSession} from '../app/session';
import {apiGet} from '../api/client';
import {useExperiments} from '../hooks/useExperiments';
import {useWorkers} from '../hooks/useWorkers';
import {useEvents} from '../hooks/useEvents';
import {PageHeader} from '../components/ui/PageHeader';
import {Stat} from '../components/ui/Stat';
import {RunCard} from '../components/experiments/RunCard';
import {EventRows} from '../components/events/EventRows';
import {QueryState} from '../components/common/QueryState';
import {EmptyState} from '../components/common/EmptyState';
import {LabQueue} from './LabQueue';
import {IS_MOCK} from '../lib/dataSource';

const activeStates=['RUNNING','STARTING','RECOVERING','PAUSING','CANCELLING','DRAINING'];
export function DashboardPage(){
 const [energyPeriod,setEnergyPeriod]=useState<'todayWh'|'monthWh'|'lifetimeWh'>('todayWh');
 const now=useObservationTime();const {t}=useProduct();const {workspace,session}=useSession();const runs=useExperiments(),workers=useWorkers(),events=useEvents();
 const operations=useQuery({queryKey:['platform-operations',session?.user.userId],queryFn:()=>apiGet<{dispatchHeld:boolean;queueCount:number;runtimeIssue:string|null;reservations:unknown[]}>('/api/v1/platform/operations'),enabled:!IS_MOCK&&!!session?.user.platformAdmin,refetchInterval:5000,retry:1});
 const experiments=runs.data??[];const devices=workers.data??[];
 const running=experiments.filter(e=>activeStates.includes(e.status));const queued=experiments.filter(e=>e.status==='QUEUED');
 const unique=new Map(devices.filter(w=>w.status==='ONLINE').map(w=>[w.physicalResourceId??w.workerId,w]));
 const power=[...unique.values()].filter(w=>w.telemetry?.gpu?.powerDrawW!=null&&now-(w.telemetry.receivedAt??w.telemetry.sampledAt)<30);
 const watts=power.reduce((sum,w)=>sum+(w.telemetry?.gpu?.powerDrawW??0),0);
 const fleet=fleetResources(devices.flatMap(w=>w.telemetry?[w.telemetry]:[]),now);
 const energy=fleet.energyComponents.length?fleet.energyComponents.reduce((sum,c)=>sum+c.energy[energyPeriod],0):null;
 const recent=[...experiments].sort((a,b)=>Number(activeStates.includes(b.status))-Number(activeStates.includes(a.status))||b.createdAt.localeCompare(a.createdAt)).slice(0,4);
 const distribution=[{name:'Active',value:running.length,color:'var(--acc)'},{name:'Queued',value:queued.length,color:'var(--warning)'},{name:'Completed',value:experiments.filter(e=>e.status==='COMPLETED').length,color:'var(--chart-secondary)'},{name:'Other states',value:experiments.filter(e=>!activeStates.includes(e.status)&&!['QUEUED','COMPLETED'].includes(e.status)).length,color:'var(--mut)'}];
 return <><PageHeader title={t('Dashboard')} description={`${workspace?.name??t('Your lab')} · ${t('Resources, experiments and system activity in one place.')}`} actions={<Link className="btn pri" to="/experiments/new">+ {t('Create experiment')}</Link>}/>
 {!workspace?<EmptyState title={t('Select a workspace')} message="Choose a workspace to view its experiments and resources."><Link className="btn pri" to="/workspace">{t('Workspaces')}</Link></EmptyState>:<QueryState isPending={runs.isPending||workers.isPending} isError={runs.isError||workers.isError} hasData={!!runs.data&&!!workers.data} title={t('Could not load the dashboard')}>
 <div className="dashboard-welcome"><div><h2>{t('Your research at a glance.')}</h2><p>{t('Contribution, connection and allocation are shown separately for each GPU.')}</p></div>{operations.data&&<Status value={operations.data.dispatchHeld?'Dispatch held':'Dispatch enabled'}/>}</div>
 {operations.data?.dispatchHeld&&<div className="note warn">{t('Dispatch is held. Queued experiments will wait until an administrator enables it.')} <Link to="/operations">{t('Lab operations')} →</Link></div>}
 {operations.data?.runtimeIssue&&<div className="note err" role="alert">{operations.data.runtimeIssue}</div>}
 <div className="stats"><Stat label={t('Active experiments')} value={running.length} note={`${queued.length} ${t('in queue')}`}/><Stat label={t('Online GPU devices')} value={unique.size} unit={`/ ${devices.length}`} note={t('Physical UUIDs are deduplicated when available')}/><Stat label={t('Contribution enabled')} value={devices.filter(w=>w.status==='ONLINE'&&w.contributionEnabled).length} note={t('Owner-approved devices that are online')}/><Stat label={t('Observed GPU power')} value={power.length?watts.toFixed(0):'—'} unit="W" note={`${power.length} ${t('GPUs reporting fresh power samples')}`}/></div>
 <section className="card fleet-energy"><div className="ch"><h2>{t('Fleet power & energy')}</h2><Link className="link" to="/workers">{t('Resource detail')} →</Link></div><div className="cb"><div className="stats"><Stat label={t('CPU package power')} value={fleet.cpuW?.toFixed(1)??'—'} unit="W" note={t('Fresh package sensors')}/><Stat label={t('Measured component subtotal')} value={fleet.componentW?.toFixed(1)??'—'} unit="W" note={t('Available components only')}/><Stat label={t('Whole machine (AC)')} value={fleet.wholeW?.toFixed(1)??'—'} unit="W" note={`${fleet.wholeCount} / ${fleet.hostCount} ${t('hosts with fresh wall meters')}`}/><Stat label={t('Cumulative energy')} value={energy==null?'—':(energy/1000).toFixed(4)} unit="kWh" note={t('Recorded observations')}/></div><label className="fleet-period">{t('Energy period')}<select value={energyPeriod} onChange={e=>setEnergyPeriod(e.target.value as typeof energyPeriod)}><option value="todayWh">{t('Today')}</option><option value="monthWh">{t('This month')}</option><option value="lifetimeWh">{t('Lifetime')}</option></select></label><p className="info-caption">{t('Available component measurements in this workspace. CPU packages and GPUs are deduplicated by hardware identity. Missing sensors and offline time are excluded; energy is not per-job billing.')}</p></div></section>
 <div className="dashboard-grid"><div className="dashboard-stack"><div className="section-title"><div><h2>{t('Recent experiments')}</h2><p>{t('Active runs appear first.')}</p></div><Link className="link" to="/experiments">{t('View all')} →</Link></div>{recent.length?<div className="resource-grid">{recent.map(e=><RunCard key={e.experimentId} experiment={e}/>)}</div>:<section className="card"><EmptyState title={t('No experiments yet')} message="Create your first experiment to start tracking progress here."><Link className="btn pri" to="/experiments/new">{t('Create experiment')}</Link></EmptyState></section>}
 {!IS_MOCK&&<LabQueue showEmpty/>}<section className="card"><div className="ch"><h2>{t('Recent events')}</h2><Link className="link" to="/events">{t('Open log')} →</Link></div>{events.isError?<div className="cb note err" role="alert">{t('Activity unavailable')}</div>:events.isPending?<div className="cb" role="status">{t('Loading…')}</div>:events.data?.length?<EventRows events={[...events.data].sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp)).slice(0,5)} label={t('Recent events')}/>:<EmptyState title={t('No events yet')}/>}</section></div>
 <div className="dashboard-stack"><section className="card"><div className="ch"><h2>{t('GPU fleet')}</h2><Link className="link" to="/workers">{t('Manage')} →</Link></div>{devices.length?devices.map(w=><article className="device-mini" key={w.workerId}><div className="device-mini-heading"><Link to={`/workers/${w.workerId}`}>{w.displayName??w.profile.gpuName}</Link><Status value={w.status}/></div><p>{w.profile.gpuName} · {(w.profile.vramTotalMb/1024).toFixed(1)} GiB</p><div className="acts"><Status value={w.contributionEnabled?'ON':'OFF'}/><Status value={w.allocatedTo?'Allocated':'Idle'}/></div><p>{w.allocatedTo?<Link to={`/experiments/${w.allocatedTo}`}>{t('Open allocated experiment')} →</Link>:t('No active allocation')}</p></article>):<EmptyState title={t('No workers registered')}/>}</section>
 <section className="card"><div className="ch"><h2>{t('Experiment states')}</h2></div><div className="cb"><div className="status-distribution" aria-hidden="true">{distribution.filter(d=>d.value).map(d=><span key={d.name} style={{flex:d.value,background:d.color}}/>)}</div><div className="status-legend">{distribution.map(d=><span key={d.name}><i style={{background:d.color}}/>{t(d.name)}<b>{d.value}</b></span>)}</div></div></section></div></div>
 </QueryState>}</>;
}

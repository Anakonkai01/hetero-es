import {useProduct,Status} from '@heteroes/product-ui';
import { LabDevices } from './LabDevices';
import { useState } from 'react';
import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query';
import { apiGet,apiPatch,apiPost } from '../api/client';
import { useSession } from '../app/session';
import { PageHeader } from '../components/ui/PageHeader';
import type { User } from '../types/access';
import type { Worker } from '../types/worker';

interface Operations {
  cloudStorageConfigured?:boolean;recoveryStorageConfigured?:boolean;
  metadataBackup?:{status:string;createdAt:number;errorType?:string}|null;
  dispatchHeld:boolean;queueCount:number;runtimeIssue:string|null;productService:string;runtimeService:string;
  quarantinedWorkerIds?:string[];workers:Worker[];
  reservations:{runId:string;status:string;failureReason?:string;workerStates:Record<string,{alive?:boolean;confirmed?:boolean}>}[];
  recentFailures?:{runId:string;status:string;failureReason:string}[];
}
interface Audit {sequence:number;actor:string;action:string;target:string;created:string;}
type Action={path:string;body?:unknown;method?:'PATCH'|'POST'};

export function LabOperationsPage() {
  const {t}=useProduct();
  const { session,refreshSession }=useSession();const cache=useQueryClient();const allowed=Boolean(session?.user.platformAdmin&&session.user.accountStatus==='ACTIVE');
  const users=useQuery({queryKey:['platform-users',session?.user.userId],queryFn:()=>apiGet<User[]>('/api/v1/platform/users'),enabled:allowed,refetchInterval:5000});
  const ops=useQuery({queryKey:['platform-operations',session?.user.userId],queryFn:()=>apiGet<Operations>('/api/v1/platform/operations'),enabled:allowed,refetchInterval:5000});
  const audit=useQuery({queryKey:['platform-audit',session?.user.userId],queryFn:()=>apiGet<Audit[]>('/api/v1/platform/audit'),enabled:allowed,refetchInterval:5000});
  const [confirmed,setConfirmed]=useState(false);
  const [notice,setNotice]=useState('');
  const action=useMutation({mutationFn:(a:Action)=>a.method==='PATCH'?apiPatch(a.path,a.body):apiPost(a.path,a.body),onSuccess:async()=>{await cache.invalidateQueries();await refreshSession();}});
  const pending=users.data?.filter(user=>user.accountStatus==='PENDING')??[];const others=users.data?.filter(user=>user.accountStatus!=='PENDING')??[];
  if (!allowed) return <p role="alert">{t("Platform administrator permission required.")}</p>;
  function update(user:User,body:unknown,message='') {setNotice('');action.mutate({path:`/api/v1/platform/users/${user.userId}`,method:'PATCH',body},{onSuccess:()=>setNotice(message)});}
  return <><PageHeader title={t("Lab operations")} description={t("Accounts, service health and safe maintenance.")} />
    {action.error && <p className="note err" role="alert">{action.error.message}</p>}
    <section className="card approvals"><div className="ch"><h2>{t("Account approval")}</h2>{pending.length>0&&<span className="count-badge" aria-label={`${pending.length} ${t('accounts waiting for approval')}`}>{pending.length}</span>}</div><div className="cb demo-form">
      {users.error && <p role="alert">{users.error.message}</p>}{users.isPending && <p>{t("Loading accounts…")}</p>}
      {notice && <p className="note ok" role="status">{notice}</p>}
      {users.data && !pending.length && <p className="hint">{t("No accounts are waiting for approval.")}</p>}
      {pending.map(user=><article className="approval-card" key={user.userId} data-account={user.username}><div><b>{user.displayName}</b><small>@{user.username} · {t("Requested an account")}</small></div><div className="acts">
        <button className="btn accent" disabled={action.isPending} onClick={()=>update(user,{accountStatus:'ACTIVE'},`${user.displayName} ${t("was approved.")}`)}>{t("Approve")}</button>
        <button className="btn" disabled={action.isPending} onClick={()=>update(user,{accountStatus:'REJECTED'},`${user.displayName} ${t("was declined.")}`)}>{t("Reject")}</button>
      </div></article>)}
      <details className="advanced-panel"><summary>{t("All accounts")} ({others.length})</summary>
      {others.map(user=><div className="request-card" key={user.userId} data-account={user.username}><div><b>{user.displayName} · {user.username}</b><small>{t(user.accountStatus??'Unknown')} · {t(user.platformAdmin?'Platform administrator':'Member')} {t("· Workspace creation")}{t(user.canCreateWorkspace?'allowed':'restricted')}</small></div><div className="acts">
        {user.accountStatus!=='ACTIVE' && <button className="btn accent" disabled={action.isPending} onClick={()=>update(user,{accountStatus:'ACTIVE'},`${user.displayName} ${t("was approved.")}`)}>{t("Approve")}</button>}
        {user.accountStatus==='ACTIVE' && user.userId!==session?.user.userId && <button className="btn dng" disabled={action.isPending} onClick={()=>{if(window.confirm(`Suspend ${user.username}? Queued jobs will be cancelled and active jobs will drain.`))update(user,{accountStatus:'SUSPENDED'});}}>{t("Suspend")}</button>}
        <details className="more-actions"><summary className="btn">{t("More")}</summary><div className="acts">
          <button className="btn" disabled={action.isPending} onClick={()=>update(user,{canCreateWorkspace:!user.canCreateWorkspace})}>{user.canCreateWorkspace?'Revoke workspace creation':'Allow workspace creation'}</button>
          <button className="btn" disabled={action.isPending} onClick={()=>action.mutate({path:`/api/v1/platform/users/${user.userId}/revoke-sessions`})}>{t("Revoke sessions")}</button>
          <button className="btn" disabled={action.isPending} onClick={()=>{if(window.confirm(`Change platform administrator permission for ${user.username}?`))update(user,{platformAdmin:!user.platformAdmin});}}>{user.platformAdmin?'Remove platform admin':'Grant platform admin'}</button>
        </div></details>
      </div></div>)}
      </details>
    </div></section>
    <LabDevices administration /><section className="card"><div className="ch"><h2>{t("Services and reservations")}</h2></div><div className="cb demo-form">
      {ops.error && <p role="alert">{ops.error.message}</p>}{ops.data && <>
        <div className="ops-tiles">
          <div><span className="hint">{t("Product service")}</span><Status value={ops.data.productService}/></div>
          <div><span className="hint">{t("Runtime service")}</span><Status value={ops.data.runtimeService}/></div>
          <div><span className="hint">{t("Queue")}</span><b>{ops.data.queueCount}</b></div>
          <div><span className="hint">{t("Dispatch")}</span><Status value={ops.data.dispatchHeld?'Dispatch held':'Dispatch enabled'}/></div>
        </div>
        {ops.data.runtimeIssue && <p className="note warn">{ops.data.runtimeIssue}</p>}
        <p><span className="hint">{t("Quarantine")}: </span>{ops.data.quarantinedWorkerIds?.join(', ')||t('None')}</p>
        {ops.data.workers.map(w=><p key={w.workerId}><b>{w.workerId}</b> · {t(w.status)} · {w.admissionReason}</p>)}
        {ops.data.reservations.length===0 && <p className="hint">{t("No active reservations.")}</p>}{ops.data.reservations.map(r=><div key={r.runId}><b>{r.runId} · {r.status}</b><p>{r.failureReason}</p>{Object.entries(r.workerStates).map(([id,state])=><p key={id}>{id}: {t(state.confirmed?'confirmed':'shutdown unknown')} · {t(state.alive===true?'Alive':state.alive===false&&state.confirmed?'Confirmed stopped':'Unknown')}</p>)}</div>)}
        {ops.data.recentFailures?.map(r=><p key={r.runId}>{r.runId} · {r.status} · {r.failureReason}</p>)}
      </>}
    </div></section>
    <section className="card"><div className="ch"><h2>{t("Backup and restore")}</h2></div><div className="cb demo-form">
      <p>{`${t('Recovery points are created between generations. Metadata backups run hourly when recovery storage is configured. Storage:')} ${(ops.data?.recoveryStorageConfigured??ops.data?.cloudStorageConfigured)?t("configured"):t("awaiting configuration")}. ${t('Restore into a new deployment using the operator guide.')}`}</p>
      {ops.data?.metadataBackup&&<p>{t("Last metadata backup:")}{" "}{ops.data.metadataBackup.status} · {new Date(ops.data.metadataBackup.createdAt*1000).toLocaleString()} {ops.data.metadataBackup.errorType}</p>}
      {ops.data?.dispatchHeld && <><label className="fg"><span><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} /> {t("I have reviewed the worker configuration and confirmed this deployment may dispatch jobs.")}</span></label><button className="btn" disabled={!confirmed||action.isPending} onClick={()=>action.mutate({path:'/api/v1/platform/maintenance/resume',body:{workerConfigurationConfirmed:true}})}>{t("Resume reviewed deployment")}</button></>}
    </div></section>
    <section className="card"><div className="ch"><h2>{t("Platform activity")}</h2></div><div className="cb">{audit.error && <p role="alert">{audit.error.message}</p>}{audit.data?.slice(0,30).map(a=><p key={a.sequence}>{a.action} · {a.actor} · {a.target} · {new Date(a.created).toLocaleString()}</p>)}</div></section>
  </>;
}

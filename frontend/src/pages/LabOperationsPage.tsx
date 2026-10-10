import { LabDevices } from './LabDevices';
import { useState } from 'react';
import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query';
import { apiGet,apiPatch,apiPost,downloadBackup } from '../api/client';
import { useSession } from '../app/session';
import { PageHeader } from '../components/ui/PageHeader';
import type { User } from '../types/access';
import type { Worker } from '../types/worker';

interface Operations {
  agentMode?:boolean;cloudStorageConfigured?:boolean;
  metadataBackup?:{status:string;createdAt:number;errorType?:string}|null;
  dispatchHeld:boolean;queueCount:number;runtimeIssue:string|null;productService:string;runtimeService:string;
  runtimeMaintenance?:boolean;quarantinedWorkerIds?:string[];workers:Worker[];
  reservations:{runId:string;status:string;failureReason?:string;workerStates:Record<string,{alive?:boolean;confirmed?:boolean}>}[];
  recentFailures?:{runId:string;status:string;failureReason:string}[];
}
interface Backup { backupId:string;sizeBytes:number; }
interface Audit {sequence:number;actor:string;action:string;target:string;created:string;}
type Action={path:string;body?:unknown;method?:'PATCH'|'POST'};

export function LabOperationsPage() {
  const { session,refreshSession }=useSession();const cache=useQueryClient();const allowed=Boolean(session?.user.platformAdmin&&session.user.accountStatus==='ACTIVE');
  const users=useQuery({queryKey:['platform-users',session?.user.userId],queryFn:()=>apiGet<User[]>('/api/v1/platform/users'),enabled:allowed,refetchInterval:5000});
  const ops=useQuery({queryKey:['platform-operations',session?.user.userId],queryFn:()=>apiGet<Operations>('/api/v1/platform/operations'),enabled:allowed,refetchInterval:5000});
  const backups=useQuery({queryKey:['platform-backups',session?.user.userId],queryFn:()=>apiGet<Backup[]>('/api/v1/platform/backups'),enabled:allowed});
  const audit=useQuery({queryKey:['platform-audit',session?.user.userId],queryFn:()=>apiGet<Audit[]>('/api/v1/platform/audit'),enabled:allowed,refetchInterval:5000});
  const [confirmed,setConfirmed]=useState(false);const [downloadError,setDownloadError]=useState('');
  const action=useMutation({mutationFn:(a:Action)=>a.method==='PATCH'?apiPatch(a.path,a.body):apiPost(a.path,a.body),onSuccess:async()=>{await cache.invalidateQueries();await refreshSession();}});
  if (!allowed) return <p role="alert">Platform administrator permission required.</p>;
  function update(user:User,body:unknown) {action.mutate({path:`/api/v1/platform/users/${user.userId}`,method:'PATCH',body});}
  return <><PageHeader title="Lab operations" description="Accounts, service health and safe maintenance." />
    {action.error && <p className="note err" role="alert">{action.error.message}</p>}
    <section className="card"><div className="ch"><h2>Account approval</h2></div><div className="cb demo-form">
      {users.error && <p role="alert">{users.error.message}</p>}{users.isPending && <p>Loading accounts…</p>}
      {users.data?.map(user=><div className="request-card" key={user.userId} data-account={user.username}><div><b>{user.displayName} · {user.username}</b><small>{user.accountStatus} · {user.platformAdmin?'Platform administrator':'Member'} · Workspace creation {user.canCreateWorkspace?'allowed':'restricted'}</small></div><div className="acts">
        {user.accountStatus!=='ACTIVE' && <button className="btn accent" disabled={action.isPending} onClick={()=>update(user,{accountStatus:'ACTIVE'})}>Approve</button>}
        {user.accountStatus==='PENDING' && <button className="btn" disabled={action.isPending} onClick={()=>update(user,{accountStatus:'REJECTED'})}>Reject</button>}
        {user.accountStatus==='ACTIVE' && user.userId!==session?.user.userId && <button className="btn dng" disabled={action.isPending} onClick={()=>{if(window.confirm(`Suspend ${user.username}? Queued jobs will be cancelled and active jobs will drain.`))update(user,{accountStatus:'SUSPENDED'});}}>Suspend</button>}
        <button className="btn" disabled={action.isPending} onClick={()=>update(user,{canCreateWorkspace:!user.canCreateWorkspace})}>{user.canCreateWorkspace?'Revoke workspace creation':'Allow workspace creation'}</button>
        <button className="btn" disabled={action.isPending} onClick={()=>action.mutate({path:`/api/v1/platform/users/${user.userId}/revoke-sessions`})}>Revoke sessions</button>
        <button className="btn" disabled={action.isPending} onClick={()=>{if(window.confirm(`Change platform administrator permission for ${user.username}?`))update(user,{platformAdmin:!user.platformAdmin});}}>{user.platformAdmin?'Remove platform admin':'Grant platform admin'}</button>
      </div></div>)}
    </div></section>
    <LabDevices administration /><section className="card"><div className="ch"><h2>Services and reservations</h2></div><div className="cb demo-form">
      {ops.error && <p role="alert">{ops.error.message}</p>}{ops.data && <><p>Product: {ops.data.productService} · Runtime: {ops.data.runtimeService}</p><p>Queue: {ops.data.queueCount} · Dispatch {ops.data.dispatchHeld?'HELD':'enabled'} · Runtime maintenance {ops.data.runtimeMaintenance?'held':'off'}</p>
        {ops.data.runtimeIssue && <p className="note warn">{ops.data.runtimeIssue}</p>}
        <p>Quarantine: {ops.data.quarantinedWorkerIds?.join(', ')||'None'}</p>
        {ops.data.workers.map(w=><p key={w.workerId}>{w.workerId} · {w.status} · {w.admissionReason}</p>)}
        {ops.data.reservations.length===0 && <p>No active reservations.</p>}{ops.data.reservations.map(r=><div key={r.runId}><b>{r.runId} · {r.status}</b><p>{r.failureReason}</p>{Object.entries(r.workerStates).map(([id,state])=><p key={id}>{id}: {state.confirmed?'confirmed':'shutdown unknown'} · {state.alive?'alive':'stopped'}</p>)}</div>)}
        {ops.data.recentFailures?.map(r=><p key={r.runId}>{r.runId} · {r.status} · {r.failureReason}</p>)}
      </>}
    </div></section>
    <section className="card"><div className="ch"><h2>Backup and restore</h2></div><div className="cb demo-form">
      <p>{ops.data?.agentMode ? `Recovery points are created between generations. Metadata backups run hourly when cloud storage is configured. Cloud storage: ${ops.data.cloudStorageConfigured?'configured':'awaiting configuration'}. Restore into a new deployment using the operator guide.` : 'Backups require confirmed idle runtime ownership and briefly hold dispatch. Restore into a new deployment directory using the operator guide.'}</p>
      {ops.data?.agentMode&&ops.data.metadataBackup&&<p>Last metadata backup: {ops.data.metadataBackup.status} · {new Date(ops.data.metadataBackup.createdAt*1000).toLocaleString()} {ops.data.metadataBackup.errorType}</p>}
      <button className="btn pri" disabled={ops.data?.agentMode||action.isPending||!ops.data||ops.data.dispatchHeld||ops.data.reservations.length>0} onClick={()=>action.mutate({path:'/api/v1/platform/backups'})}>{action.isPending?'Operation in progress…':'Create idle backup'}</button>
      {backups.error && <p role="alert">{backups.error.message}</p>}{backups.data?.map(b=><div key={b.backupId}><span className="mono">{b.backupId}</span> · {(b.sizeBytes/1024/1024).toFixed(1)} MB <button className="btn" onClick={()=>void downloadBackup(b.backupId).catch(e=>setDownloadError(e instanceof Error?e.message:'Download failed'))}>Download backup</button></div>)}
      {downloadError && <p role="alert">{downloadError}</p>}
      {(ops.data?.dispatchHeld||ops.data?.runtimeMaintenance) && <><label className="fg"><span><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} /> I have reviewed the worker configuration and confirmed this deployment may dispatch jobs.</span></label><button className="btn" disabled={!confirmed||action.isPending} onClick={()=>action.mutate({path:'/api/v1/platform/maintenance/resume',body:{workerConfigurationConfirmed:true}})}>Resume reviewed deployment</button></>}
    </div></section>
    <section className="card"><div className="ch"><h2>Platform activity</h2></div><div className="cb">{audit.error && <p role="alert">{audit.error.message}</p>}{audit.data?.slice(0,30).map(a=><p key={a.sequence}>{a.action} · {a.actor} · {a.target} · {new Date(a.created).toLocaleString()}</p>)}</div></section>
  </>;
}

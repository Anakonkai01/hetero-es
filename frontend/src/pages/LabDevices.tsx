import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPatch } from '../api/client';
import { useSession } from '../app/session';

export interface Device {
  deviceId:string;workerId:string;displayName:string;ownerUserId:string;approvalStatus:string;
  bootId:string|null;lastSeen:number;connectionStatus:string;contributionEnabled:boolean;
  workspaceId:string|null;selfTest:{gpuName:string;vramTotalMb:number;coordinator:boolean;passed:boolean};
}

export function LabDevices({ administration=false }: {administration?:boolean}) {
  const {session}=useSession();const cache=useQueryClient();
  const capabilities=useQuery({queryKey:['device-capabilities'],queryFn:()=>apiGet<{agentMode?:boolean}>('/api/v1/health')});
  const enabled=Boolean(capabilities.data?.agentMode);
  const devices=useQuery({queryKey:['devices',session?.user.userId,administration],queryFn:()=>apiGet<Device[]>(administration?'/api/v1/platform/devices':'/api/v1/devices'),enabled,refetchInterval:3000});
  const [code,setCode]=useState('');const [workspace,setWorkspace]=useState('lab');
  const action=useMutation({mutationFn:(a:{path:string;body?:unknown;patch?:boolean})=>a.patch?apiPatch(a.path,a.body):apiPost(a.path,a.body),onSuccess:()=>cache.invalidateQueries()});
  if (!enabled) return null;
  return <section className="card"><div className="ch"><h2>{administration?'Device approval':'My devices'}</h2></div><div className="cb demo-form">
    {action.error && <p className="note err" role="alert">{action.error.message}</p>}
    {devices.error && <p role="alert">{devices.error.message}</p>}
    {!administration && <><button className="btn" onClick={()=>void apiPost<{code:string}>('/api/v1/devices/pairing-codes').then(r=>setCode(r.code)).catch(e=>setCode(e.message))}>Create pairing code</button>{code && <p className="mono">{code}</p>}<p className="hint">Pairing codes expire after ten minutes. Run enrollment in the device agent, then request administrator approval.</p></>}
    {administration && <label className="fg">Approval workspace<select className="sel" value={workspace} onChange={e=>setWorkspace(e.target.value)}>{session?.workspaces.map(w=><option value={w.workspaceId} key={w.workspaceId}>{w.name}</option>)}</select></label>}
    {devices.data?.map(d=><div className="request-card" key={d.deviceId} data-device={d.workerId}><div><b>{d.displayName} · {d.selfTest.gpuName}</b><small>{d.workerId} · {d.approvalStatus} · {d.connectionStatus} · Contribution {d.contributionEnabled?'ON':'OFF'}</small><small>Last seen: {d.lastSeen?new Date(d.lastSeen*1000).toLocaleString():'Never'} · {d.selfTest.coordinator?'Coordinator capable':'Worker'} · {d.workspaceId??'Unassigned'}</small></div><div className="acts">
      {administration && d.approvalStatus==='PENDING' && <button className="btn accent" disabled={action.isPending||!d.selfTest.passed} onClick={()=>action.mutate({path:'/api/v1/platform/devices/'+d.deviceId,patch:true,body:{approved:true,workspaceId:workspace}})}>Approve device</button>}
      {administration && d.approvalStatus==='APPROVED' && <button className="btn dng" disabled={action.isPending} onClick={()=>{if(window.confirm('Revoke this device and request safe cancellation?'))action.mutate({path:'/api/v1/platform/devices/'+d.deviceId,patch:true,body:{approved:false}});}}>Revoke device</button>}
      {d.ownerUserId===session?.user.userId && d.approvalStatus==='APPROVED' && <button className="btn" disabled={action.isPending||!d.bootId||d.connectionStatus!=='ONLINE'} onClick={()=>action.mutate({path:'/api/v1/devices/'+d.deviceId+'/contribution',body:{enabled:!d.contributionEnabled,bootId:d.bootId}})}>Turn {d.contributionEnabled?'OFF':'ON'}</button>}
    </div></div>)}
    <p className="hint">Contribution starts OFF after each agent restart. Offline devices keep their reservations until owned processes are confirmed stopped.</p>
  </div></section>;
}

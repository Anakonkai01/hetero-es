import { useState } from 'react';
import { useMutation,useQueryClient } from '@tanstack/react-query';
import { apiDelete,apiPatch,apiPost } from '../api/client';
import { useSession } from '../app/session';
import { useResources } from '../hooks/useAccess';

export function LabMembership() {
  const {workspace,refreshSession}=useSession();const query=useResources();const cache=useQueryClient();const [username,setUsername]=useState('');
  const mutation=useMutation({mutationFn:(input:{path:string;method:'POST'|'PATCH'|'DELETE';body?:unknown})=>input.method==='DELETE'?apiDelete(input.path):input.method==='PATCH'?apiPatch(input.path,input.body):apiPost(input.path,input.body),onSuccess:async()=>{await cache.invalidateQueries();await refreshSession();setUsername('');}});
  const admin=workspace?.role==='ADMIN';const prefix=`/api/v1/workspaces/${workspace?.workspaceId}`;
  return <section className="card"><div className="ch"><h2>Members</h2></div><div className="cb demo-form">
    <p>{admin?'Workspace administrators can view and cancel all workspace experiments.':'You can view your own experiments.'}</p>
    {admin && <form className="demo-form" onSubmit={e=>{e.preventDefault();mutation.mutate({path:prefix+'/invitations',method:'POST',body:{username}});}}><label className="fg">Invite by username<input className="inp" required minLength={3} maxLength={64} value={username} onChange={e=>setUsername(e.target.value)} /></label><button className="btn accent" disabled={mutation.isPending}>Invite member</button></form>}
    {mutation.error && <p className="note err" role="alert">{mutation.error.message}</p>}{mutation.isSuccess && <p role="status">Membership operation saved.</p>}
    {query.data?.members.map(m=><div className="request-card" key={m.user.userId}><span>{m.user.displayName} · {m.user.username} · {m.role}</span>{admin && <div className="acts"><button className="btn" disabled={mutation.isPending} onClick={()=>mutation.mutate({path:prefix+'/members/'+m.user.userId,method:'PATCH',body:{role:m.role==='ADMIN'?'PARTICIPANT':'ADMIN'}})}>{m.role==='ADMIN'?'Make participant':'Make administrator'}</button><button className="btn dng" disabled={mutation.isPending} onClick={()=>{if(window.confirm(`Remove ${m.user.username}? Their queued jobs will be cancelled and active jobs will drain.`))mutation.mutate({path:prefix+'/members/'+m.user.userId,method:'DELETE'});}}>Remove member</button></div>}</div>)}
  </div></section>;
}

import {useProduct} from '@heteroes/product-ui';
import { useState } from 'react';
import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query';
import { apiGet,apiPost } from '../api/client';
import { useSession } from '../app/session';
import type { User } from '../types/access';

interface Contribution {worker_id:string;owner:string;workspace_id:string|null;enabled:boolean;}

export function LabContributions() {
  const {t}=useProduct();
  const {session}=useSession();const cache=useQueryClient();
  const query=useQuery({queryKey:['contributions',session?.user.userId],queryFn:()=>apiGet<Contribution[]>('/api/v1/contributions'),enabled:session?.user.accountStatus==='ACTIVE',refetchInterval:5000});
  return <section className="card"><div className="ch"><h2>{t("GPU contribution")}</h2></div><div className="cb demo-form"><p>{t("Turning contribution off cancels queued jobs and drains active work. Moving or enabling a GPU requires confirmed idle shutdown.")}</p>
    {query.error && <p role="alert">{query.error.message}</p>}{query.data?.length===0 && <p>{t("No owned GPUs. A platform administrator assigns configured GPU ownership.")}</p>}
    {query.data?.map(c=><ContributionCard key={c.worker_id} contribution={c} refresh={()=>cache.invalidateQueries()} />)}
  </div></section>;
}

function ContributionCard({contribution:c,refresh}:{contribution:Contribution;refresh:()=>Promise<unknown>}) {
  const {t}=useProduct();
  const {session}=useSession();const [workspaceId,setWorkspace]=useState(c.workspace_id??session?.workspaces[0]?.workspaceId??'');
  const [owner,setOwner]=useState(c.owner);
  const users=useQuery({queryKey:['platform-users',session?.user.userId],queryFn:()=>apiGet<User[]>('/api/v1/platform/users'),enabled:Boolean(session?.user.platformAdmin)});
  const mutation=useMutation({mutationFn:(enabled:boolean)=>apiPost(`/api/v1/contributions/${c.worker_id}`,{enabled,workspaceId,...(session?.user.platformAdmin&&enabled?{ownerUserId:owner}:{})}),onSuccess:refresh});
  return <div className="request-card" data-contribution={c.worker_id}><div><b>{c.worker_id}</b><p>{t("Contribution")}{c.enabled?t("ON"):t("OFF")} {t("· Workspace")}{session?.workspaces.find(w=>w.workspaceId===c.workspace_id)?.name??c.workspace_id??'None'}</p></div><div className="demo-form">
    <label className="fg">{t("Contributing workspace")}<select className="sel" value={workspaceId} onChange={e=>setWorkspace(e.target.value)}><option value="">{t("Choose workspace")}</option>{session?.workspaces.map(w=><option key={w.workspaceId} value={w.workspaceId}>{w.name}</option>)}</select></label>
    {session?.user.platformAdmin && <label className="fg">{t("GPU owner")}<select className="sel" value={owner} onChange={e=>setOwner(e.target.value)}>{users.data?.filter(u=>u.accountStatus==='ACTIVE').map(u=><option key={u.userId} value={u.userId}>{u.username}</option>)}</select></label>}
    <div className="acts"><button className="btn accent" disabled={mutation.isPending||!workspaceId} onClick={()=>mutation.mutate(true)}>{t("Enable / assign")}</button><button className="btn" disabled={mutation.isPending||!c.enabled} onClick={()=>mutation.mutate(false)}>{t("Turn off and drain")}</button></div>{mutation.error && <p role="alert">{mutation.error.message}</p>}
  </div></div>;
}

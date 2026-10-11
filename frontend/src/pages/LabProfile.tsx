import {useProduct} from '@heteroes/product-ui';
import { useState } from 'react';
import { useMutation,useQuery,useQueryClient } from '@tanstack/react-query';
import { apiGet,apiPatch,apiPost } from '../api/client';
import { useSession } from '../app/session';
import { PageHeader } from '../components/ui/PageHeader';
import type { User,WorkspaceInvitation } from '../types/access';

export function LabProfile() {
  const {t}=useProduct();
  const {session,refreshSession}=useSession();const user=session!.user;const cache=useQueryClient();
  const [displayName,setName]=useState(user.displayName);const [email,setEmail]=useState(user.email??'');const [bio,setBio]=useState(user.bio??'');
  const [currentPassword,setCurrent]=useState('');const [newPassword,setNew]=useState('');
  const profile=useMutation({mutationFn:()=>apiPatch<User>('/api/v1/profile',{displayName,email,bio}),onSuccess:refreshSession});
  const password=useMutation({mutationFn:()=>apiPost('/api/v1/auth/password',{currentPassword,newPassword}),onSuccess:()=>{setCurrent('');setNew('');}});
  const revoke=useMutation({mutationFn:()=>apiPost('/api/v1/auth/revoke-other-sessions')});
  const invitations=useQuery({queryKey:['lab-invitations',user.userId],queryFn:()=>apiGet<WorkspaceInvitation[]>('/api/v1/my-invitations'),enabled:user.accountStatus==='ACTIVE',refetchInterval:5000});
  const accept=useMutation({mutationFn:(id:string)=>apiPost(`/api/v1/my-invitations/${id}/accept`),onSuccess:async()=>{await refreshSession();await cache.invalidateQueries({queryKey:['lab-invitations']});}});
  return <><PageHeader title={t("Profile")} description={`${t('Account status:')} ${t(user.accountStatus??'Unknown')}`} />
    <section className="card"><div className="ch"><h2>{user.username}</h2></div><form className="cb demo-form" onSubmit={e=>{e.preventDefault();profile.mutate();}}>
      <label className="fg">{t("Display name")}<input className="inp" required maxLength={100} value={displayName} onChange={e=>setName(e.target.value)} /></label>
      <label className="fg">{t("Email")}<input className="inp" type="email" maxLength={200} value={email} onChange={e=>setEmail(e.target.value)} /></label>
      <label className="fg">{t("About you")}<textarea className="inp" maxLength={1000} value={bio} onChange={e=>setBio(e.target.value)} /></label>
      {profile.error && <p role="alert">{profile.error.message}</p>}{profile.isSuccess && <p role="status">{t("Profile saved.")}</p>}<button className="btn pri" disabled={profile.isPending}>{t("Save profile")}</button>
    </form></section>
    <section className="card"><div className="ch"><h2>{t("Security")}</h2></div><form className="cb demo-form" onSubmit={e=>{e.preventDefault();password.mutate();}}>
      <label className="fg">{t("Current password")}<input className="inp" type="password" autoComplete="current-password" required value={currentPassword} onChange={e=>setCurrent(e.target.value)} /></label>
      <label className="fg">{t("New password")}<input className="inp" type="password" autoComplete="new-password" required minLength={12} maxLength={200} value={newPassword} onChange={e=>setNew(e.target.value)} /></label>
      <p className="hint">{t("Changing your password signs out all other sessions.")}</p>{password.error && <p role="alert">{password.error.message}</p>}{password.isSuccess && <p role="status">{t("Password changed.")}</p>}
      <button className="btn pri" disabled={password.isPending}>{t("Change password")}</button><button type="button" className="btn" disabled={revoke.isPending} onClick={()=>revoke.mutate()}>{t("Sign out other sessions")}</button>
      {revoke.error && <p role="alert">{revoke.error.message}</p>}{revoke.isSuccess && <p role="status">{t("Other sessions revoked.")}</p>}
    </form></section>
    {user.accountStatus==='ACTIVE' && <section className="card"><div className="ch"><h2>{t("Workspace invitations")}</h2></div><div className="cb demo-form">
      {invitations.isPending && <p>{t("Loading invitations…")}</p>}{invitations.error && <p role="alert">{invitations.error.message}</p>}
      {invitations.data?.length===0 && <p>{t("No pending invitations.")}</p>}{invitations.data?.map(i=><div key={i.invitationId}><b>{i.workspaceName}</b> <button className="btn accent" disabled={accept.isPending} onClick={()=>accept.mutate(i.invitationId)}>{t("Accept invitation")}</button></div>)}
      {accept.error && <p role="alert">{accept.error.message}</p>}
    </div></section>}
  </>;
}

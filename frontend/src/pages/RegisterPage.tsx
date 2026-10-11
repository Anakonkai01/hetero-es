import {useProduct,ProductMark,PreferencesControl} from '@heteroes/product-ui';
import { useState, type FormEvent } from 'react';
import { Link, Navigate } from 'react-router';
import { apiPost } from '../api/client';
import { useSession } from '../app/session';

export function RegisterPage() {
  const {t}=useProduct();
  const { session, signIn } = useSession();
  const [username,setUsername]=useState(''); const [displayName,setName]=useState('');
  const [password,setPassword]=useState(''); const [error,setError]=useState(''); const [sending,setSending]=useState(false);
  async function submit(event:FormEvent) {
    event.preventDefault();setSending(true);setError('');
    try { await apiPost('/api/v1/auth/register',{username,displayName,password});await signIn({username,password}); }
    catch(error) { setError(error instanceof Error ? error.message : 'Registration failed'); }
    finally { setSending(false); }
  }
  if (session) return <Navigate to="/workspace" replace />;
  return <div className="auth-layout"><aside className="auth-story"><Link className="public-brand" to="/"><ProductMark/>HeteroES</Link><div><span className="eyebrow">{t('Research together')}</span><h1>{t('A shared space.')}<br/>{t('For your next experiment.')}</h1><p>{t('Connect your resources, track every experiment and build on your progress.')}</p></div><Link to="/">← {t('Back to home')}</Link></aside><main className="auth-main"><div className="auth-tools"><PreferencesControl/></div><section className="auth-form"><span className="eyebrow">HETEROES LAB</span><h1>{t("Join this lab")}</h1><form className="demo-form" onSubmit={submit}>
    <p>{t("Your account starts pending. A platform administrator approves access to GPU resources.")}</p>
    <label className="fg">{t("Username")}<input className="inp" required minLength={3} maxLength={64} pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]*" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} /></label>
    <label className="fg">{t("Display name")}<input className="inp" required maxLength={100} value={displayName} onChange={e=>setName(e.target.value)} /></label>
    <label className="fg">{t("Password")}<input className="inp" type="password" required minLength={12} maxLength={200} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)} /></label>
    <p className="hint">{t("Use at least 12 characters.")}</p>{error && <p className="note err" role="alert">{error}</p>}
    <button className="btn pri auth-submit" disabled={sending}>{sending ? t("Registering…") : t("Register")}</button><Link to="/login">{t("Back to sign in")}</Link>
  </form></section><footer className="auth-bottom">HeteroES · {t('Local lab, connected resources.')}</footer></main></div>;
}

import { useState, type FormEvent } from 'react';
import { Link, Navigate } from 'react-router';
import { apiPost } from '../api/client';
import { useSession } from '../app/session';

export function RegisterPage() {
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
  return <div className="app auth-screen"><section className="card auth-card"><div className="ch"><h1>Join this lab</h1></div><form className="cb demo-form" onSubmit={submit}>
    <p>Your account starts pending. A platform administrator approves access to GPU resources.</p>
    <label className="fg">Username<input className="inp" required minLength={3} maxLength={64} pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]*" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} /></label>
    <label className="fg">Display name<input className="inp" required maxLength={100} value={displayName} onChange={e=>setName(e.target.value)} /></label>
    <label className="fg">Password<input className="inp" type="password" required minLength={12} maxLength={200} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)} /></label>
    <p className="hint">Use at least 12 characters.</p>{error && <p className="note err" role="alert">{error}</p>}
    <button className="btn pri" disabled={sending}>{sending ? 'Registering…' : 'Register'}</button><Link to="/login">Back to sign in</Link>
  </form></section></div>;
}

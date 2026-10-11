import {PreferencesControl,ProductMark,useProduct} from '@heteroes/product-ui';
import {useState,type FormEvent} from 'react';
import {Link,Navigate} from 'react-router';
import {useSession} from '../app/session';
import {LoadingState} from '../components/common/LoadingState';
import {IS_MOCK} from '../lib/dataSource';

export function LoginPage(){
 const {t}=useProduct();const {session,pending,signIn}=useSession();
 const [username,setUsername]=useState('');const [password,setPassword]=useState('');const [show,setShow]=useState(false);const [sending,setSending]=useState(false);const [error,setError]=useState('');
 async function submit(event:FormEvent){event.preventDefault();setSending(true);setError('');try{await signIn({username,password});}catch(e){setError(e instanceof Error?e.message:t('Could not sign in.'));}finally{setSending(false);}}
 if(pending)return <div className="app auth-screen"><LoadingState/></div>;
 if(session)return <Navigate to="/workspace" replace/>;
 return <div className="auth-layout"><aside className="auth-story"><Link className="public-brand" to="/"><ProductMark/>HeteroES</Link><div><span className="eyebrow">{t('Research together')}</span><h1>{t('Your lab.')}<br/>{t('Your next discovery.')}</h1><p>{t('Connect your resources, track every experiment and build on your progress.')}</p><div className="auth-art" aria-hidden="true">{[2,4,3,6,5,8,7,10,9,12].map((h,i)=><span key={i} style={{height:`${h*12}px`}}/>)}</div><span className="auth-story-caption">EVOLUTION STRATEGIES · DISTRIBUTED COMPUTE</span></div><Link to="/">← {t('Back to home')}</Link></aside>
 <main className="auth-main"><div className="auth-tools"><PreferencesControl/></div><section className="auth-form"><span className="eyebrow">HETEROES LAB</span><h1>{t('Welcome back.')}</h1><p className="auth-description">{t('Sign in to your lab to continue your research.')}</p><form onSubmit={submit} className="demo-form">
 {IS_MOCK&&<div className="note warn">{t('Simulated authentication using MSW. Use sample accounts only; do not enter a real password.')}</div>}
 <label className="fg">{t('Username')}<input className="inp" autoFocus autoComplete="username" placeholder={t('Your username')} required value={username} onChange={e=>setUsername(e.target.value)}/></label>
 <label className="fg">{t('Password')}<span className="password-field"><input className="inp" type={show?'text':'password'} autoComplete={IS_MOCK?'off':'current-password'} placeholder={t('Your password')} required value={password} onChange={e=>setPassword(e.target.value)}/><button type="button" aria-label={t(show?'Hide password':'Show password')} onClick={()=>setShow(!show)}>{t(show?'Hide':'Show')}</button></span></label>
 {error&&<div className="note err" role="alert">{error}</div>}
 <button type="submit" className="btn pri auth-submit" disabled={sending}>{t(sending?'Signing in…':'Sign in')} <span aria-hidden="true">→</span></button>
 {IS_MOCK?<p className="hint">{t('Accounts:')} admin, an, binh · demo-local</p>:<p className="auth-register">{t('New to this lab?')} <Link to="/register">{t('Create an account')}</Link></p>}
 </form><div className="auth-help">{t('Your administrator approves access to shared resources.')}<br/><Link to="/">{t('Learn how the lab works')} ↗</Link></div></section><footer className="auth-bottom">HeteroES · {t('Local lab, connected resources.')}</footer></main></div>;
}

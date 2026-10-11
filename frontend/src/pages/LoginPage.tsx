import {useProduct} from '@heteroes/product-ui';
import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router";
import { useSession } from "../app/session";
import { LoadingState } from "../components/common/LoadingState";
import { IS_MOCK } from "../lib/dataSource";
import {PreferencesControl} from '@heteroes/product-ui';

export function LoginPage() {
  const {t}=useProduct();
  const { session, pending, signIn } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSending(true);
    setError("");
    try { await signIn({ username, password }); }
    catch (error) { setError(error instanceof Error ? error.message : "Could not sign in."); }
    finally { setSending(false); }
  }

  if (pending) return <div className="app auth-screen"><LoadingState /></div>;
  if (session) return <Navigate to="/workspace" replace />;
  return <div className="app auth-screen">
    <section className="card auth-card"><div className="auth-brand"><span className="brand-symbol">{t("H")}</span><span>{t("HeteroES")}<span className="hint">{t('Research together')}</span></span></div><PreferencesControl/>
      <div className="ch"><h1>{t("HeteroES ·")}{IS_MOCK ? t("Local demo") : t("Runtime")}</h1></div>
      <form className="cb demo-form" onSubmit={submit}>
        <p>{t("Sign in to manage workspaces, request GPU workers and prepare experiments.")}</p>
        {IS_MOCK && <div className="note warn">{t("Simulated authentication using MSW. Use sample accounts only; do not enter a real password.")}</div>}
        <label className="fg">{t("Username")}<input className="inp" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
        <label className="fg">{t("Password")}<input className="inp" type="password" autoComplete={IS_MOCK ? "off" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        {IS_MOCK ? <div className="hint">{t("Accounts:")}<b>{t("admin")}</b>, <b>{t("an")}</b>, <b>{t("binh")}</b> {t("· Roles vary by workspace")}<br />{t("Public demo password for all three:")}<b>{t("demo-local")}</b></div> : <p className="hint">{t("New to this lab?")}<Link to="/register">{t("Register an account")}</Link>{t(". A platform administrator approves resource access.")}</p>}
        {error && <div className="note err" role="alert">{error}</div>}
        <button className="btn pri" disabled={sending}>{sending ? t("Signing in…") : t("Sign in")}</button>
      </form>
    </section>
  </div>;
}

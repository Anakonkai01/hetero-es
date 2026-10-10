import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { useSession } from "../app/session";
import { LoadingState } from "../components/common/LoadingState";
import { IS_MOCK } from "../lib/dataSource";

export function LoginPage() {
  const { session, pending, signIn } = useSession();
  const [username, setUsername] = useState("admin");
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
    <section className="card auth-card">
      <div className="ch"><h1>HeteroES · {IS_MOCK ? "Local demo" : "Runtime"}</h1></div>
      <form className="cb demo-form" onSubmit={submit}>
        <p>Sign in to manage workspaces, request GPU workers and prepare experiments.</p>
        {IS_MOCK && <div className="note warn">Simulated authentication using MSW. Use sample accounts only; do not enter a real password.</div>}
        <label className="fg">Username<input className="inp" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
        <label className="fg">Password<input className="inp" type="password" autoComplete={IS_MOCK ? "off" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        {IS_MOCK ? <div className="hint">Accounts: <b>admin</b>, <b>an</b>, <b>binh</b> · Roles vary by workspace<br />Public demo password for all three: <b>demo-local</b></div> : <p className="hint">Accounts: admin and participant. Use the credentials provisioned on the coordinator host.</p>}
        {error && <div className="note err" role="alert">{error}</div>}
        <button className="btn pri" disabled={sending}>{sending ? "Signing in…" : "Sign in"}</button>
      </form>
    </section>
  </div>;
}

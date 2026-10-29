"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BriefcaseBusiness, LogOut, ShieldCheck, Users } from "lucide-react";
import AdminWorkspace from "@/components/layout/admin-workspace";
import { GhostArt } from "@/components/recruiter/ghost-art";
import { GhostMascot } from "@/components/recruiter/ghost-mascot";
import { RecruiterWorkspace } from "@/components/recruiter/workspace";
import { AsapChatOverlay } from "@/components/recruiter/asap-chat-overlay";
import { api } from "@/lib/api";
import "@/components/recruiter/recruiter.css";

const pipelineSteps = [
  "High-volume CV parsing & talent extraction",
  "Criterion-level evidence verification",
  "Side-by-side candidate matrix benchmarking",
  "Targeted technical interview kits",
];

export default function Home() {
  const cache = useQueryClient();
  const session = useQuery({queryKey: ["workspace-session"], queryFn: () => api.session(), retry: false, refetchOnReconnect: false});
  const [sessionExpired, setSessionExpired] = useState(false);
  const [fadingLogin, setFadingLogin] = useState(false);

  useEffect(() => {
    const expire = () => setSessionExpired(true);
    window.addEventListener("atos-session-expired", expire);
    return () => window.removeEventListener("atos-session-expired", expire);
  }, []);

  useEffect(() => {
    if (fadingLogin) {
      const timer = setTimeout(() => setFadingLogin(false), 400);
      return () => clearTimeout(timer);
    }
  }, [fadingLogin]);

  const [role, setRole] = useState<"admin" | "user">("user");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function logout() {
    setBusy(true);
    try {
      await api.logout();
      setSessionExpired(false);
      setFadingLogin(false);
      try { sessionStorage.removeItem("atos_workspace_session_active"); } catch {}
      if (typeof window !== "undefined" && window.location.search) {
        window.history.replaceState(null, "", window.location.pathname);
      }
      cache.clear();
      setPassword("");
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign out.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const value = await api.login(role, password);
      try { sessionStorage.removeItem("atos_workspace_session_active"); } catch {}
      if (typeof window !== "undefined" && window.location.search) {
        window.history.replaceState(null, "", window.location.pathname);
      }
      setFadingLogin(true);
      cache.setQueryData(["workspace-session"], value);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  if (session.isPending) return <div className="recruiter r-loading" role="status">Opening your workspace…</div>;

  const reauthentication = session.data?.role ? <SessionReauthentication active={sessionExpired} role={session.data.role} onSignedIn={() => {
    setSessionExpired(false);
    void cache.invalidateQueries({predicate: query => query.queryKey[0] !== "workspace-session"});
  }} onSignOut={logout}/> : null;

  const loginOverlay = fadingLogin ? (
    <div
      className="recruiter r-login r-login-exit"
      data-theme="dark"
      aria-hidden="true"
      onAnimationEnd={() => setFadingLogin(false)}
    >
      <section className="r-login-story">
        <div className="r-login-header">
          <div className="r-login-company">
            <span className="r-brand-mark small">a</span>
            <span className="r-company-name">atos</span>
          </div>
          <div className="r-login-pipeline-brand">
            <span className="r-ghost" aria-hidden="true"><GhostArt id="ghost-fading-login" /></span>
            <div className="r-login-pipeline-meta">
              <span className="r-asap-wordmark">ASAP</span>
              <span className="r-pipeline-title">AI Screening &amp; Assessment Pipeline</span>
            </div>
          </div>
        </div>
        <div className="r-login-intro">
          <h1>Objective screening.<br/>Defensible decisions.</h1>
          <p>Automate high-volume CV parsing, verify role criteria against cited resume proof, and benchmark candidates side-by-side with full auditability.</p>
          <div className="r-login-flow">
            {pipelineSteps.map((label, i) => <div key={label}><span>{i + 1}</span>{label}</div>)}
          </div>
        </div>
        <p className="r-login-footer">Strict resume traceability · Auditable decision gating</p>
      </section>
      <section className="r-login-form">
        <div className="r-login-form-body">
          <BriefcaseBusiness className="r-login-icon" size={28}/>
          <h2>Welcome back</h2>
          <p>Opening your workspace…</p>
          <fieldset className="r-role-picker" disabled>
            <legend>Workspace</legend>
            {(["user", "admin"] as const).map(value => (
              <label key={value} className={role === value ? "selected" : ""}>
                <input type="radio" name="role-fading" value={value} checked={role === value} readOnly/>
                {value === "user" ? <Users size={22}/> : <ShieldCheck size={22}/>}
                <strong>{value === "user" ? "User" : "Admin"}</strong>
                <small>{value === "user" ? "Recruiter workspace" : "Full platform access"}</small>
              </label>
            ))}
          </fieldset>
          <button className="r-button primary r-login-submit" disabled>
            Opening workspace…<ArrowRight size={18}/>
          </button>
        </div>
      </section>
    </div>
  ) : null;

  if (session.data?.role === "admin") {
    return (
      <>
        <div className="r-workspace-enter">
          <AdminWorkspace />
          <button className="r-admin-exit" onClick={logout} disabled={busy}><LogOut size={16}/> Sign out of Admin</button>
          {error && <div className="r-admin-error" role="alert">{error}</div>}
          {reauthentication}
        </div>
        <AsapChatOverlay />
        {loginOverlay}
      </>
    );
  }

  if (session.data?.role === "user") {
    return (
      <>
        <div className="r-workspace-enter">
          <RecruiterWorkspace onLogout={logout} />
          {reauthentication}
        </div>
        <AsapChatOverlay />
        {loginOverlay}
      </>
    );
  }

  return (
    <div className="recruiter r-login" data-theme="dark">
      <section className="r-login-story">
        <div className="r-login-header">
          <div className="r-login-company">
            <span className="r-brand-mark small">a</span>
            <span className="r-company-name">atos</span>
          </div>
          <div className="r-login-pipeline-brand">
            <GhostMascot activityKey="login" />
            <div className="r-login-pipeline-meta">
              <span className="r-asap-wordmark">ASAP</span>
              <span className="r-pipeline-title">AI Screening &amp; Assessment Pipeline</span>
            </div>
          </div>
        </div>
        <div className="r-login-intro">
          <h1>Objective screening.<br/>Defensible decisions.</h1>
          <p>Automate high-volume CV parsing, verify role criteria against cited resume proof, and benchmark candidates side-by-side with full auditability.</p>
          <div className="r-login-flow">
            {pipelineSteps.map((label, i) => <div key={label}><span>{i + 1}</span>{label}</div>)}
          </div>
        </div>
        <p className="r-login-footer">Strict resume traceability · Auditable decision gating</p>
      </section>
      <section className="r-login-form">
        <form onSubmit={handleLogin}>
          <BriefcaseBusiness className="r-login-icon" size={28}/>
          <h2>Welcome back</h2>
          <p>Choose your workspace to continue.</p>
          <fieldset className="r-role-picker">
            <legend>Workspace</legend>
            {(["user", "admin"] as const).map(value => (
              <label key={value} className={role === value ? "selected" : ""}>
                <input type="radio" name="role" value={value} checked={role === value} onChange={() => setRole(value)}/>
                {value === "user" ? <Users size={22}/> : <ShieldCheck size={22}/>}
                <strong>{value === "user" ? "User" : "Admin"}</strong>
                <small>{value === "user" ? "Recruiter workspace" : "Full platform access"}</small>
              </label>
            ))}
          </fieldset>
          <label className="r-field">Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password"/></label>
          {(error || session.isError) && <div className="r-alert" role="alert">{error || "Cannot connect to the backend. Start the API and try signing in again."}</div>}
          <button className="r-button primary r-login-submit" disabled={busy}>{busy ? "Signing in…" : "Open workspace"}<ArrowRight size={18}/></button>
        </form>
      </section>
      <AsapChatOverlay />
    </div>
  );
}

function SessionReauthentication({active, role, onSignedIn, onSignOut}: {active: boolean; role: "admin" | "user"; onSignedIn: () => void; onSignOut: () => Promise<void>}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (active && !dialog.current?.open) dialog.current?.showModal();
    if (!active) dialog.current?.close();
  }, [active]);
  return <dialog ref={dialog} className="recruiter r-session-dialog" aria-labelledby="session-expired-title" onCancel={event => event.preventDefault()}>
    <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError("");
      try {await api.login(role, password); setPassword(""); onSignedIn();}
      catch (error) {setError(error instanceof Error ? error.message : "Unable to sign in.");}
      finally {setBusy(false);}
    }}>
      <h2 id="session-expired-title">Sign in to continue</h2>
      <p>Your session has expired. Your current form stays open. Sign in, then retry the action.</p>
      <label className="r-field">{role === "admin" ? "Admin" : "User"} password<input type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)}/></label>
      {error && <div className="r-alert" role="alert">{error}</div>}
      <button className="r-button primary" disabled={busy}>{busy ? "Signing in…" : "Sign in again"}</button>
      <button type="button" className="r-button subtle" disabled={busy} onClick={() => void onSignOut()}>Sign out</button>
    </form>
  </dialog>;
}

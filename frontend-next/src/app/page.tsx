"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BriefcaseBusiness, LogOut, ShieldCheck, Users } from "lucide-react";
import AdminWorkspace from "@/components/layout/admin-workspace";
import { RecruiterWorkspace } from "@/components/recruiter/workspace";
import { api } from "@/lib/api";
import "@/components/recruiter/recruiter.css";

export default function Home() {
  const cache = useQueryClient();
  const session = useQuery({queryKey: ["workspace-session"], queryFn: () => api.session(), retry: false});
  const [role, setRole] = useState<"admin" | "user">("user");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    setBusy(true);
    try { await api.logout(); cache.clear(); setPassword(""); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not sign out."); }
    finally { setBusy(false); }
  }
  if (session.isPending) return <div className="recruiter r-loading" role="status">Opening your workspace…</div>;
  if (session.data?.role === "admin") return <><AdminWorkspace /><button className="r-admin-exit" onClick={logout} disabled={busy}><LogOut size={16}/> Sign out of Admin</button>{error && <div className="r-admin-error" role="alert">{error}</div>}</>;
  if (session.data?.role === "user") return <RecruiterWorkspace onLogout={logout} />;
  return <div className="recruiter r-login" data-theme="dark">
    <section className="r-login-story">
      <div className="r-brand"><span className="r-brand-mark">a</span><span>atos<span className="r-brand-divider"/>Talent screening</span></div>
      <div className="r-login-intro"><span className="r-pill">Recruitment workspace</span><h1>More clarity.<br/>Better conversations.</h1><p>Move from a stack of CVs to a considered shortlist. Keep the evidence close and the final decision human.</p>
        <div className="r-login-flow">{["Define the role", "Find the strongest matches", "Review the evidence", "Prepare the interview"].map((label, i) => <div key={label}><span>{i + 1}</span>{label}</div>)}</div>
      </div><p className="r-login-footer">Built around your next hiring decision.</p>
    </section>
    <section className="r-login-form"><form onSubmit={async e => {
      e.preventDefault(); setBusy(true); setError("");
      try { const value = await api.login(role, password); cache.setQueryData(["workspace-session"], value); }
      catch (e) { setError(e instanceof Error ? e.message : "Unable to sign in."); }
      finally { setBusy(false); }
    }}>
      <BriefcaseBusiness className="r-login-icon" size={28}/><h2>Welcome back</h2><p>Choose your workspace to continue.</p>
      <fieldset className="r-role-picker"><legend>Workspace</legend>{(["user", "admin"] as const).map(value => <label key={value} className={role === value ? "selected" : ""}><input type="radio" name="role" value={value} checked={role === value} onChange={() => setRole(value)}/>{value === "user" ? <Users size={22}/> : <ShieldCheck size={22}/>}<strong>{value === "user" ? "User" : "Admin"}</strong><small>{value === "user" ? "Recruiter workspace" : "Full platform access"}</small></label>)}</fieldset>
      <label className="r-field">Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password"/></label>
      {(error || session.isError) && <div className="r-alert" role="alert">{error || "Cannot connect to the backend. Start the API and try signing in again."}</div>}
      <button className="r-button primary r-login-submit" disabled={busy}>{busy ? "Signing in…" : "Open workspace"}<ArrowRight size={18}/></button>
      <small className="r-demo-note">Local demo access · Shared password: 1234</small>
    </form></section>
  </div>;
}

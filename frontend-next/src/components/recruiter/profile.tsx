"use client";
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import { PreScreenRow } from "@/types";
import { message } from "./common";
import { ParsedProfile, ExtractedData } from "./parsed-profile";
import { downloadJson } from "./common";

export function ProfileDialog({id, row, onClose}: {id: string; row?: PreScreenRow; onClose: () => void}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const profile = useQuery({queryKey: ["recruiter-profile", id], queryFn: () => api.getCandidate(id)});
  useEffect(() => {const element = dialog.current; element?.showModal(); return () => element?.close();}, []);
  return <dialog ref={dialog} className="recruiter r-profile-dialog" onClose={onClose} aria-labelledby="candidate-title"><header><div><span className="r-muted">Candidate profile</span><h2 id="candidate-title">{profile.data?.masked_name || "Candidate"}</h2></div><button className="r-icon-button" aria-label="Close profile" onClick={onClose}><X size={20}/></button></header><div className="r-profile-content">
    {profile.isPending && <p role="status">Loading CV…</p>}{profile.error && <p role="alert">{message(profile.error)}</p>}
    {row && <><h3>Pre-screen breakdown</h3><div className="r-score-breakdown">{[["Composite", row.pre_screen_score], ["Similarity", row.similarity_score], ["Required skills", row.skills_score], ["Experience", row.experience_score], ["Education", row.degree_score]].map(([label, value]) => <div key={label}><small>{label}</small><strong>{typeof value === "number" ? `${value.toFixed(1)}%` : "Not required"}</strong></div>)}</div><ul className="r-checks">{row.checks.map((check,i) => <li key={i}>{check}</li>)}</ul>{row.error && <p className="r-alert">Deep evaluation failed: {row.error}</p>}{row.deep_evaluation && <><h3>Deep evaluation · {row.deep_evaluation.overall_score.toFixed(1)} / 100</h3>{row.deep_evaluation.requirement_matches.map(match => <div className="r-evidence" key={match.requirement_id}><strong>{match.title || match.requirement_id}</strong><span className="r-pill">{match.status.replaceAll("_", " ")}</span><p>{match.reasoning}</p>{match.citations.map((citation,i) => <blockquote key={i}>{citation.quote}<small>{citation.verified ? "Verified CV quote" : "Quote needs verification"}</small></blockquote>)}</div>)}</> }</>}
    {profile.data && <><h3>Extracted profile</h3>{profile.data.parsed_cv ? <ParsedProfile profile={profile.data.parsed_cv}/> : <div className="r-tags">{profile.data.skills.map((skill,i) => <span key={i}>{skill}</span>)}</div>}
      <details className="r-profile-section"><summary>Anonymized CV evidence</summary><pre className="r-cv-text">{profile.data.sanitized_text || "No CV text available."}</pre></details>
      {row?.deep_evaluation && <details className="r-profile-section"><summary>Complete evaluation details</summary><ExtractedData value={row.deep_evaluation}/></details>}
      <details className="r-profile-section"><summary>Export profile</summary><button className="r-button" onClick={() => downloadJson(profile.data?.parsed_cv, `candidate-${id}.json`)}>Download structured CV</button></details>
    </>}
  </div></dialog>;
}

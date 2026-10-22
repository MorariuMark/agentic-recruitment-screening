"use client";
import React, { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { api } from "@/lib/api";
import { PreScreenRow } from "@/types";
import { message } from "./common";
import { ParsedProfile, ExtractedData } from "./parsed-profile";
import { RequirementEvidence } from "./requirement-evidence";
import { downloadJson } from "./common";
import { sourceSpans } from "@/lib/evidence";

interface ProfileDialogProps {
  id: string;
  row?: PreScreenRow;
  initialQuote?: string;
  onClose: () => void;
}

function HighlightedCvText({ text, query }: { text: string; query?: string }) {
  if (!query || !query.trim() || !text) {
    return <pre className="r-cv-text">{text || "No CV text available."}</pre>;
  }
  const spans = sourceSpans(text, query);
  if (!spans.length) return <><p role="status" className="r-alert">This quotation could not be located in the original CV. Review the source before relying on it.</p><pre className="r-cv-text">{text}</pre></>;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  for (const [idx, end] of spans) {
    if (idx > lastIndex) {
      parts.push(text.slice(lastIndex, idx));
    }
    parts.push(
      <mark key={idx} className="r-cv-highlight">
        {text.slice(idx, end)}
      </mark>
    );
    lastIndex = end;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <pre className="r-cv-text">{parts}</pre>;
}

export function ProfileDialog({ id, row, initialQuote, onClose }: ProfileDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cvSectionRef = useRef<HTMLDetailsElement>(null);
  const [highlightQuote, setHighlightQuote] = useState(initialQuote || "");
  const profile = useQuery({
    queryKey: ["recruiter-profile", id],
    queryFn: () => api.getCandidate(id),
  });

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    if (initialQuote) {
      setHighlightQuote(initialQuote);
      if (cvSectionRef.current) {
        cvSectionRef.current.open = true;
      }
    }
  }, [initialQuote]);

  useEffect(() => {
    if (!highlightQuote || !profile.data || !cvSectionRef.current) return;
    const section = cvSectionRef.current;
    section.open = true;
    const frame = requestAnimationFrame(() => {
      (section.querySelector("mark") || section).scrollIntoView({block: "center", behavior: "auto"});
    });
    return () => cancelAnimationFrame(frame);
  }, [highlightQuote, profile.data]);

  function handleQuoteClick(quote: string) {
    setHighlightQuote(quote);
    if (cvSectionRef.current) {
      cvSectionRef.current.open = true;
      cvSectionRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }

  const rec = row?.deep_evaluation?.recommendation;
  const recPillClass =
    rec === "strong_match"
      ? "success"
      : rec === "borderline"
      ? "warning"
      : "alert-pill";

  return (
    <dialog
      ref={dialog}
      className="recruiter r-profile-dialog"
      onClose={() => {
        if (!dialog.current?.open) onClose();
      }}
      aria-labelledby="candidate-title"
    >
      <header>
        <div>
          <span className="r-muted">Candidate profile</span>
          <h2 id="candidate-title">{profile.data?.masked_name || "Candidate"}</h2>
        </div>
        <button className="r-icon-button" aria-label="Close profile" onClick={onClose}>
          <X size={20} />
        </button>
      </header>
      <div className="r-profile-content">
        {profile.isPending && <p role="status">Loading CV…</p>}
        {profile.error && <p role="alert">{message(profile.error)}</p>}
        {row && (
          <>
            <h3>Pre-screen breakdown</h3>
            <div className="r-score-breakdown">
              {(row.pipeline_version === "v2"
                ? [
                    ["Pre-screen", `${row.pre_screen_score.toFixed(1)} / 100`],
                    ["Required supported", `${row.essential_supported} / ${row.essential_total}`],
                    ["Unknown required", String(row.essential_unknown || 0)],
                    ["Contradicted required", String(row.essential_contradicted || 0)],
                  ]
                : [
                    ["Composite", row.pre_screen_score],
                    ["Similarity", row.similarity_score],
                    ["Required skills", row.skills_score],
                    ["Experience", row.experience_score],
                    ["Education", row.degree_score],
                  ]
              ).map(([label, value]) => (
                <div key={label}>
                  <small>{label}</small>
                  <strong>
                    {typeof value === "number"
                      ? `${value.toFixed(1)}%`
                      : typeof value === "string"
                      ? value
                      : "Not required"}
                  </strong>
                </div>
              ))}
            </div>
            <ul className="r-checks">
              {row.checks.map((check, i) => (
                <li key={i}>{check}</li>
              ))}
            </ul>
            {row.error && <p className="r-alert">Deep evaluation failed: {row.error}</p>}
            {row.deep_evaluation && (
              <>
                <div className="r-deep-summary-header">
                  <h3>
                    Deep evaluation · {row.deep_evaluation.overall_score.toFixed(1)} / 100
                  </h3>
                  {rec && (
                    <span className={`r-pill ${recPillClass}`}>
                      {rec.replaceAll("_", " ")}
                    </span>
                  )}
                </div>
                {row.deep_evaluation.requirement_matches.map((match) => {
                  const statusClass =
                    match.status === "met"
                      ? "success"
                      : match.status === "clarification_needed"
                      ? "warning"
                      : "alert-pill";
                  return (
                    <div className="r-evidence" key={match.requirement_id}>
                      <div className="r-evidence-head">
                        <strong>{match.title || match.requirement_id}</strong>
                        <span className={`r-pill ${statusClass}`}>
                          {match.status.replaceAll("_", " ")}
                        </span>
                      </div>
                      <p>{match.reasoning}</p>
                      {match.citations.map((citation, i) => (
                        <blockquote
                          key={i}
                          className="r-clickable-quote"
                          tabIndex={0}
                          role="button"
                          title="Click to view and highlight quote in CV text"
                          onClick={() => handleQuoteClick(citation.quote)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              handleQuoteClick(citation.quote);
                            }
                          }}
                        >
                          <span className="r-quote-text">“{citation.quote}”</span>
                          <small>
                            {citation.verified ? "✓ Verified CV quote" : "⚠ Quote needs verification"} · Jump to CV text
                          </small>
                        </blockquote>
                      ))}
                    </div>
                  );
                })}
              </>
            )}
          </>
        )}
        {!!row?.requirement_assessments?.length && (
          <>
            <h3>Job requirement evidence</h3>
            <RequirementEvidence assessments={row.requirement_assessments} />
          </>
        )}
        {profile.data && (
          <>
            <h3>Extracted profile</h3>
            {profile.data.parsed_cv ? (
              <ParsedProfile profile={profile.data.parsed_cv} />
            ) : (
              <div className="r-tags">
                {profile.data.skills.map((skill, i) => (
                  <span key={i}>{skill}</span>
                ))}
              </div>
            )}
            <details
              ref={cvSectionRef}
              className="r-profile-section"
              open={!!highlightQuote || undefined}
            >
              <summary>
                Anonymized CV evidence
                {highlightQuote && <small>1 citation highlighted</small>}
              </summary>
              <HighlightedCvText
                text={profile.data.sanitized_text || ""}
                query={highlightQuote}
              />
            </details>
            {row?.deep_evaluation && (
              <details className="r-profile-section">
                <summary>Complete evaluation details</summary>
                <ExtractedData value={row.deep_evaluation} />
              </details>
            )}
            <details className="r-profile-section">
              <summary>Export profile</summary>
              <button
                className="r-button"
                onClick={() =>
                  downloadJson(profile.data?.parsed_cv, `candidate-${id}.json`)
                }
              >
                Download structured CV
              </button>
            </details>
          </>
        )}
      </div>
    </dialog>
  );
}

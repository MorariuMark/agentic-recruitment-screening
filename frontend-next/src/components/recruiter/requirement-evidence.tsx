import {RequirementAssessment} from "@/types";

export function RequirementEvidence({assessments}: {assessments: RequirementAssessment[]}) {
  return <div className="r-requirement-evidence">{assessments.map(item => <details className="r-profile-section" key={item.requirement_id}>
    <summary>{item.title} <span className={`r-pill ${item.status === "supported" ? "success" : item.status === "contradicted" ? "warning" : ""}`}>{item.status}</span></summary>
    <p>{item.reasoning}</p>
    {item.evidence.map(evidence => <blockquote key={evidence.id}>{evidence.text}<small>{evidence.section} · {evidence.strength === "listed" ? "Listed claim" : "Documented evidence"}</small></blockquote>)}
    {!item.evidence.length && <small>No supporting passage found. This does not prove the requirement is absent.</small>}
  </details>)}</div>;
}

import { ParsedCV } from "@/types";

const labels: Record<string, string> = {
  contact_info: "Contact details", full_name: "Name", phone_number: "Phone", linkedin_url: "LinkedIn", github_url: "GitHub / portfolio",
  education: "Education", experiences: "Work experience", certifications: "Certifications", languages: "Languages",
  projects: "Projects", publications: "Publications", patents: "Patents", logistics: "Availability & logistics",
  custom_sections: "Additional sections", miscellaneous: "Other extracted details", unused_details: "Other source content",
  audit_metadata: "Processing details", degree_title: "Degree", institution_name: "Institution", work_description: "Responsibilities",
};
const label = (key: string) => labels[key] || key.replaceAll("_", " ").replace(/^./, c => c.toUpperCase());
function hasValue(value: unknown): boolean {
  if (value == null || value === "") return false;
  if (Array.isArray(value)) return value.some(hasValue);
  if (typeof value === "object") return Object.values(value).some(hasValue);
  return true;
}

/** Render every field from the original extraction contract without discarding additions. */
export function ExtractedData({value}: {value: unknown}) {
  if (!hasValue(value)) return <span className="r-muted">Not stated</span>;
  if (Array.isArray(value)) {
    return value.every(item => typeof item === "string")
      ? <ul className="r-data-list">{value.map((item, i) => <li key={i}>{item}</li>)}</ul>
      : <div className="r-data-records">{value.map((item, i) => <div className="r-data-record" key={i}><ExtractedData value={item}/></div>)}</div>;
  }
  if (typeof value === "object" && value !== null) return <dl className="r-data-fields">{Object.entries(value).filter(([, item]) => hasValue(item)).map(([key, item]) => <div key={key}><dt>{label(key)}</dt><dd><ExtractedData value={item}/></dd></div>)}</dl>;
  return <span>{typeof value === "boolean" ? value ? "Yes" : "No" : String(value)}</span>;
}

export function ParsedProfile({profile}: {profile: ParsedCV}) {
  const sections = Object.entries(profile).filter(([key, value]) => !["raw_text", "summary", "skills"].includes(key) && hasValue(value));
  return <div className="r-parsed-profile">
    {profile.summary && <p className="r-profile-summary">{profile.summary}</p>}
    {!!profile.skills.length && <div className="r-tags">{profile.skills.map((skill, i) => <span key={i}>{skill}</span>)}</div>}
    {sections.map(([key, value]) => <details className="r-profile-section" key={key}>
      <summary>{label(key)}{Array.isArray(value) && <small>{value.length}</small>}</summary>
      <ExtractedData value={value}/>
    </details>)}
    {profile.raw_text && <details className="r-profile-section"><summary>Original extracted CV text</summary><pre className="r-cv-text">{profile.raw_text}</pre></details>}
  </div>;
}

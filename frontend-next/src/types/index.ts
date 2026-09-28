/**
 * Core Data Contracts for Agentic Recruitment Screening Platform
 */

export type RequirementCategory = "must_have" | "nice_to_have";
export type Recommendation = "strong_match" | "borderline" | "reject";

export interface JobRequirement {
  id: string;
  title: string;
  category: RequirementCategory;
  weight: number;
  description: string;
  minimum_years_experience?: number | null;
}

export interface JobDescription {
  id: string;
  title: string;
  department?: string | null;
  seniority_level?: string | null;
  location?: string | null;
  work_model?: string | null;
  employment_type?: string | null;
  requirements: JobRequirement[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CandidateExperience {
  job_title: string;
  company_name: string;
  start_date?: string | null;
  end_date?: string | null;
  work_description: string[];
  skills_used: string[];
}

export interface CandidateEducation {
  institution_name: string;
  degree_name: string;
  field_of_study?: string | null;
  graduation_year?: string | null;
}

export interface CandidateSummary {
  id: string;
  candidate_id?: string;
  masked_name: string;
  original_filename?: string | null;
  email?: string;
  skills: string[];
  total_years_experience?: number | null;
  chunks_indexed: number;
  created_at: string;
  latest_evaluation?: {
    overall_score: number;
    must_have_score: number;
    recommendation: "strong_match" | "borderline" | "reject";
    must_have_gaps_count: number;
    citation_verification_score: number;
    hitl_validated: boolean;
  } | null;
}

export interface CandidateDetail {
  id: string;
  masked_name?: string | null;
  original_filename?: string | null;
  sanitized_text?: string | null;
  skills: string[];
  experiences: Array<Record<string, any>>;
  educations: Array<Record<string, any>>;
  total_years_experience?: number | null;
  chunks_indexed: number;
  created_at?: string | null;
  latest_evaluation?: {
    evaluation_id?: string;
    overall_score: number;
    must_have_score: number;
    nice_to_have_score?: number;
    recommendation: "strong_match" | "borderline" | "reject";
    must_have_gaps_count: number;
    citation_verification_score: number;
    hitl_validated: boolean;
  } | null;
}

export interface VerbatimCitation {
  quote: string;
  source_section?: string | null;
  verified: boolean;
}

export interface RequirementMatch {
  requirement_id: string;
  status: "met" | "partial" | "not_met";
  score: number;
  confidence: number;
  reasoning: string;
  citations: VerbatimCitation[];
  gap_analysis?: string | null;
}

export interface MatchEvaluationResult {
  id: string;
  candidate_id: string;
  job_id: string;
  overall_score: number;
  must_have_score: number;
  nice_to_have_score: number;
  recommendation: "strong_match" | "borderline" | "reject";
  requirement_matches: RequirementMatch[];
  must_have_gaps_count: number;
  citation_verification_score: number;
  hitl_validated: boolean;
  recruiter_notes?: string | null;
  created_at?: string;
}

export interface InterviewQuestion {
  question_id: string;
  target_requirement_id: string;
  question_text: string;
  expected_answer_rubric: string;
  difficulty: "junior" | "mid" | "senior" | "principal";
  rationale_for_asking: string;
  target_duration_minutes: number;
}

export interface InterviewPlan {
  id: string;
  candidate_id: string;
  job_id: string;
  total_duration_minutes: number;
  executive_summary: string;
  questions: InterviewQuestion[];
}

export interface BatchCandidateResult {
  candidate_id?: string;
  filename: string;
  status: "COMPLETED" | "FAILED";
  chunks_indexed?: number;
  skills_count?: number;
  overall_score?: number;
  must_have_score?: number;
  nice_to_have_score?: number;
  recommendation?: "strong_match" | "borderline" | "reject";
  must_have_gaps_count?: number;
  citation_verification_score?: number;
  error?: string;
}

export interface BatchJobStatus {
  batch_id: string;
  job_id?: string | null;
  status: "PROCESSING" | "COMPLETED" | "PARTIAL" | "FAILED";
  total_files: number;
  processed_files: number;
  failed_files: number;
  progress_percentage: number;
  results: BatchCandidateResult[];
  created_at?: string;
  updated_at?: string;
}

export interface LLMSettings {
  active_provider: string;
  active_model: string;
  compatibility_mode: string;
  providers_catalog: Record<string, any>;
  api_keys_configured: Record<string, boolean>;
  fallback_enabled: boolean;
  fallback_chain: string[];
}

export interface RequirementComparisonCell {
  status: "met" | "partial" | "not_met";
  score: number;
  reasoning: string;
  citation_quote?: string | null;
}

export interface RequirementComparisonRow {
  requirement_id: string;
  title: string;
  category: RequirementCategory;
  weight: number;
  candidate_cells: Record<string, RequirementComparisonCell>;
}

export interface CandidateComparisonSummaryItem {
  candidate_id: string;
  masked_name: string;
  original_filename?: string | null;
  overall_score: number;
  must_have_score: number;
  nice_to_have_score: number;
  recommendation: Recommendation;
  must_have_gaps_count: number;
  citation_verification_score: number;
  hitl_validated: boolean;
}

export interface CandidateComparisonReport {
  job_id: string;
  job_title: string;
  candidates: CandidateComparisonSummaryItem[];
  matrix: RequirementComparisonRow[];
  top_recommended_id?: string | null;
  comparative_analysis: string;
}

export interface ComplianceDossier {
  compliance_standard: string;
  risk_classification: string;
  system_identity: {
    name: string;
    version: string;
    vendor: string;
    intended_purpose: string;
  };
  record_metadata: {
    dossier_generated_at: string;
    evaluation_id: string;
    candidate_id: string;
    candidate_alias: string;
    job_requisition_id: string;
    job_title: string;
    department?: string | null;
    cryptographic_sha256_seal: string;
  };
  article_9_risk_management: {
    status: string;
    risks_identified: string[];
    mitigations_implemented: string[];
  };
  article_10_data_governance: {
    status: string;
    pii_redaction_enforced: boolean;
    protected_attributes_scrubbed: string[];
    demographic_data_isolation: string;
    vector_store_cleanliness: string;
  };
  article_11_technical_documentation: {
    status: string;
    retrieval_architecture: string;
    embedding_model: string;
    inference_model: string;
    inference_temperature: number;
    structured_output_mode: string;
    multi_tier_failover: string;
  };
  article_12_record_keeping: {
    status: string;
    immutable_logging: string;
    audit_timestamp: string;
    data_integrity_hash: string;
  };
  article_13_transparency_and_explainability: {
    status: string;
    scoring_formula: string;
    overall_match_score: number;
    must_have_score: number;
    nice_to_have_score: number;
    must_have_gaps_count: number;
    citation_verification_score: number;
    total_citations_extracted: number;
    verbatim_verified_citations: number;
    unmet_gaps_documented: Array<{
      requirement_id: string;
      gap_analysis?: string | null;
      reasoning?: string | null;
    }>;
  };
  article_14_human_oversight: {
    human_in_the_loop_mandatory: boolean;
    is_decision_finalized_by_human: boolean;
    recruiter_decision: string;
    recruiter_audit_notes: string;
    algorithmic_recommendation: string;
    human_override_exercised: boolean;
    human_oversight_article: string;
  };
  article_15_accuracy_and_cybersecurity: {
    status: string;
    adversarial_prompt_injection_defense: string;
    scanned_pdf_integrity_check: string;
    failover_redundancy: string;
  };
}


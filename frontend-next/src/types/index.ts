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

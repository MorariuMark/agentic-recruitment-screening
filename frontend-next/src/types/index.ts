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
  raw_text?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ContactInfo {
  full_name: string;
  email?: string | null;
  phone_number?: string | null;
  phone?: string | null;
  location?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
}

export interface WorkExperience {
  job_title: string;
  company_name: string;
  start_date?: string | null;
  end_date?: string | null;
  duration_months?: number | null;
  work_description: string[];
  skills_used: string[];
  location?: string | null;
  work_model?: string | null;
  employment_type?: string | null;
  is_promotion?: boolean;
}

export interface Education {
  degree_title: string;
  field_of_study?: string | null;
  institution_name: string;
  graduation_year?: number | null;
  gpa_or_grade?: string | null;
  honors?: string | null;
  thesis_title?: string | null;
  location?: string | null;
}

export interface Project {
  project_name: string;
  description: string[];
  technologies: string[];
  start_date?: string | null;
  end_date?: string | null;
  project_url?: string | null;
}

export interface LanguageSkill {
  language: string;
  proficiency?: string | null;
}

export interface CustomSection {
  section_title: string;
  items: string[];
  is_relevant: boolean;
}

export interface Publication {
  title: string;
  authors?: string[];
  journal_or_conference?: string | null;
  year?: number | null;
  doi_or_url?: string | null;
}

export interface Patent {
  title: string;
  patent_number?: string | null;
  patent_office?: string | null;
  status?: string | null;
  issue_date?: string | null;
}

export interface LogisticalInfo {
  notice_period?: string | null;
  earliest_start_date?: string | null;
  relocation_preference?: string | null;
  travel_willingness?: string | null;
  salary_expectation?: string | null;
  work_authorization?: string | null;
  security_clearance?: string | null;
}

export interface ParsedCV {
  contact_info: ContactInfo;
  summary?: string | null;
  skills: string[];
  experiences: WorkExperience[];
  education: Education[];
  certifications: string[];
  projects: Project[];
  languages: LanguageSkill[];
  publications?: Publication[];
  patents?: Patent[];
  logistics?: LogisticalInfo | null;
  custom_sections?: CustomSection[];
  miscellaneous?: string[];
  unused_details?: string[];
  raw_text?: string;
}

export interface AnonymizedCandidate {
  candidate_id: string;
  anonymized_work_experiences: WorkExperience[];
  anonymized_education: Education[];
  anonymized_skills: string[];
  anonymized_certifications: string[];
  anonymized_projects: Project[];
  anonymized_languages: LanguageSkill[];
  anonymized_publications?: Publication[];
  anonymized_patents?: Patent[];
  logistics?: LogisticalInfo | null;
  anonymized_custom_sections?: CustomSection[];
  anonymized_miscellaneous?: string[];
  sanitized_text: string;
  demographic_data?: Record<string, any>;
}

export interface CVUploadResponse {
  candidate_id: string;
  parsed_cv: ParsedCV;
  anonymized_candidate: AnonymizedCandidate;
  chunks_indexed: number;
  token_usage?: TokenUsageInfo | null;
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
  parsed_cv?: ParsedCV | null;
  anonymized_candidate?: AnonymizedCandidate | null;
}

export interface VerbatimCitation {
  quote: string;
  source_section?: string | null;
  verified: boolean;
}

export type MatchStatus = "met" | "partial" | "clarification_needed" | "not_met";

export interface RequirementMatch {
  requirement_id: string;
  title?: string | null;
  jd_summary?: string | null;
  jd_citation?: string | null;
  status: "met" | "partial" | "clarification_needed" | "not_met";
  score: number;
  confidence: number;
  reasoning: string;
  citations: VerbatimCitation[];
  gap_analysis?: string | null;
  is_objective?: boolean;
  clarification_question?: string | null;
  transferable_skill?: string | null;
  benefit_of_doubt?: boolean;
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
  clarification_count?: number;
  citation_verification_score: number;
  hitl_validated: boolean;
  recruiter_notes?: string | null;
  created_at?: string;
  token_usage?: TokenUsageInfo | null;
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

export interface ModelCatalogInfo {
  id: string;
  name: string;
  provider: string;
  free: boolean;
  rate_limits: string;
  context_window: string;
  category: string;
  compatibility: string;
  description: string;
}

export interface ProviderCatalogInfo {
  id: string;
  name: string;
  icon?: string;
  description: string;
  api_key_url: string;
  default_model: string;
  default_base_url?: string;
  env_key_var: string;
  models: ModelCatalogInfo[];
}

export interface FallbackHierarchyItem {
  provider: string;
  model: string;
  name?: string;
  free?: boolean;
  rate_limits?: string | null;
}

export interface HardwareProfile {
  ram_total_gb: number;
  ram_avail_gb: number;
  gpus: Array<{
    name: string;
    vram_total_mb: number;
    vram_free_mb: number;
    vram_total_gb: number;
  }>;
  recommended_context_window: number;
  recommended_options: number[];
  recommendation_reason: string;
  current_settings: {
    context_window: number;
    rolling_context: boolean;
    thinking_enabled: boolean;
  };
}

export interface LLMSettings {
  active_provider: string;
  active_model: string;
  compatibility_mode: string;
  providers_catalog: Record<string, ProviderCatalogInfo>;
  api_keys_configured: Record<string, boolean>;
  fallback_enabled: boolean;
  fallback_chain: string[];
  custom_fallback_chain?: FallbackHierarchyItem[] | null;
  last_fallback_event?: {
    timestamp: number;
    from_provider: string;
    from_model: string;
    to_provider: string;
    to_model: string;
    error?: string;
  } | null;
  local_context_window?: number;
  local_rolling_context?: boolean;
  local_thinking_enabled?: boolean;
  hardware_profile?: HardwareProfile | null;
}

export interface RequirementComparisonCell {
  status: "met" | "partial" | "clarification_needed" | "not_met";
  score: number;
  reasoning: string;
  citation_quote?: string | null;
  clarification_question?: string | null;
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

export interface TokenUsageInfo {
  provider: string;
  model: string;
  display_name?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  status?: string;
}

export interface ModelUsageStat {
  model_key: string;
  provider: string;
  model: string;
  name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  requests: number;
  percentage_of_total: number;
  avg_latency_ms: number;
  tokens_per_second: number;
  free: boolean;
}

export interface ActivityHeatmapItem {
  date: string;
  count: number;
  tokens: number;
  level: number;
}

export interface DailyUsageTrend {
  date: string;
  label: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  requests: number;
}

export interface TokenUsageAnalytics {
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_requests: number;
  active_models_count: number;
  avg_latency_ms: number;
  active_days: number;
  model_breakdown: ModelUsageStat[];
  activity_heatmap: ActivityHeatmapItem[];
  daily_trend: DailyUsageTrend[];
  recent_logs: Array<{
    id: string;
    timestamp: string;
    provider: string;
    model: string;
    model_name: string;
    action: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    latency_ms: number;
    status: string;
  }>;
}



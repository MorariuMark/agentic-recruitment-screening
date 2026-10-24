/**
 * Core Data Contracts for Agentic Recruitment Screening Platform
 */

export type RequirementCategory = "must_have" | "nice_to_have" | "soft_skill";
export type Recommendation = "strong_match" | "borderline" | "reject";

export interface OperationTiming {
  id: string; operation: string; label: string;
  status: "running" | "completed" | "partial" | "failed" | "cancelled" | "interrupted" | "deferred";
  parent_id: string | null; batch_id: string | null; run_id: string | null;
  job_id: string | null; candidate_id: string | null;
  started_at: string; finished_at: string | null; duration_ms: number | null;
  item_count: number; completed_count: number; failed_count: number; cached: boolean;
}

export interface OperationStatistics {
  summary: Array<{operation: string; label: string; count: number; completed: number;
    failed: number; partial: number; cancelled: number; running: number; interrupted: number; deferred: number; cached: number;
    average_ms: number | null; min_ms: number | null; max_ms: number | null;
    total_ms: number; items: number; success_rate: number | null; items_per_minute: number | null}>;
  history: OperationTiming[]; total: number; limit: number; offset: number; has_more: boolean;
}

export interface WorkspaceStatistics {
  cv_parsing?: {sample_count: number; average_ms: number | null; estimates: Array<{cv_count: number; duration_ms: number | null}>};
  candidates: number; jobs: number; screening_runs: number; evaluations: number; interview_plans: number;
  cv_text_characters: number; batch_files: number; batch_processed: number; batch_failed: number;
  model_calls: number; tokens: number; model_duration_ms: number; model_average_ms: number;
  recent_screening?: Array<{run_id: string; pipeline_version: string; timings_ms?: Record<string,number>; cache_hits?: number; cache_misses?: number; reranked_candidates?: number; reranker_fallback?: boolean}>;
}

export interface PreScreenRow {
  retrieval_score?: number | null;
  assessment_method?: "literal" | "semantic";
  initial_evidence_score?: number | null;
  core_score?: number;
  role_anchor_score?: number;
  technical_score?: number | null;
  eligibility_status?: "eligible" | "clarification_needed" | "ineligible";
  eligibility_gaps?: string[];
  action_recommendation?: string | null;
  job_grounding_coverage?: number;
  tied_with_previous?: boolean;
  knockout_failed?: boolean;
  language_priority?: number;
  pipeline_version?: "v1" | "v2";
  requirement_assessments?: RequirementAssessment[];
  essential_supported?: number;
  essential_total?: number;
  essential_unknown?: number;
  essential_contradicted?: number;
  rerank_score?: number | null;
  reranked?: boolean;
  initial_rank?: number | null;
  candidate_id: string;
  rank: number;
  pre_screen_score: number;
  similarity_score: number;
  skills_score: number | null;
  experience_score: number | null;
  degree_score: number | null;
  checks: string[];
  deep_status: "not_selected" | "pending" | "completed" | "failed" | "deferred";
  deep_requirement_matches?: RequirementMatch[];
  retry_after?: number | null;
  deep_evaluation: MatchEvaluationResult | null;
  error?: string | null;
}
export interface RequirementAssessment {
  concept_results?: Array<{alternatives: string[]; score: number; role_anchor: boolean; evidence_ids: string[]}>;
  criterion_source_verified?: boolean | null;
  requirement_id: string; title: string; category: string; weight: number;
  status: "supported" | "partial" | "contradicted" | "unknown" | "not_evidenced"; score: number; reasoning: string;
  evidence: Array<{id: string; section: string; text: string; strength: "demonstrated" | "listed"}>;
  documented_years?: number | null; rerank_score?: number | null;
}
export interface ScreeningRun {
  active_candidate_id?: string;
  criteria_preparation_pending?: boolean;
  ranking_policy_version?: string;
  evidence_policy_version?: string;
  dataset?: "recruiting" | "benchmark";
  pipeline_version?: "v1" | "v2";
  phase?: string;
  ended_at?: number;
  attempt?: number;
  profile_hashes?: Record<string,string>;
  diagnostics?: {version?: string; warnings?: string[]; timings_ms?: Record<string,number>; cache_hits?: number; cache_misses?: number; evaluations_reused?: number; reranker_model?: string; reranker_fallback?: boolean; reranked_candidates?: number};
  duplicates?: Array<{candidate_id: string; kept_candidate_id: string; reason: "same_name" | "identical_evaluation" | "same_document_or_contact"}>;
  started_at?: number;
  id: string;
  job_id: string;
  job: JobDescription;
  status: "ranking" | "evaluating" | "completed" | "partial" | "failed" | "cancelled";
  top_k: number;
  deep_enabled: boolean;
  deep_candidate_ids?: string[];
  rows: PreScreenRow[];
  shortlist_ids: string[];
  decisions: Record<string, {decision: "interview" | "hold" | "reject"; notes: string}>;
  interviews?: Record<string, InterviewPlan>;
  error?: string | null;
}

export interface JobRequirement {
  id: string;
  title: string;
  category: RequirementCategory;
  weight: number;
  description: string;
  minimum_years_experience?: number | null;
  eligibility_evidence?: string | null;
  source_quote?: string | null;
  source_verified?: boolean | null;
  is_knockout?: boolean;
  concept_operator?: "all" | "any";
  evidence_plan?: {kind: string; basis_hash?: string | null; groups: Array<{alternatives: string[]; source_quote: string; role_anchor: boolean}>} | null;
}

export interface JobDescription {
  id: string;
  title: string;
  department?: string | null;
  seniority_level?: string | null;
  location?: string | null;
  work_model?: string | null;
  employment_type?: string | null;
  languages?: string[];
  custom_sections?: unknown[];
  unused_details?: string[];
  requirements: JobRequirement[];
  raw_text?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  audit_metadata?: ActionAuditInfo | null;
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
  audit_metadata?: ActionAuditInfo | null;
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
  is_benchmark?: boolean;
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
    recommendation: Recommendation;
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
  relevant?: boolean | null;
}

export type MatchStatus = "met" | "partial" | "clarification_needed" | "not_met" | "not_evidenced";

export interface RequirementMatch {
  assessment_method?: "literal" | "semantic" | "specialized";
  criterion_source_verified?: boolean | null;
  criterion_warning?: string | null;
  clarification_target?: "candidate" | "recruiter" | null;
  category?: RequirementCategory | null;
  requirement_id: string;
  title?: string | null;
  jd_summary?: string | null;
  jd_citation?: string | null;
  status: "met" | "partial" | "clarification_needed" | "not_met" | "not_evidenced";
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
  core_score?: number;
  role_anchor_score?: number;
  technical_score?: number | null;
  eligibility_status?: "eligible" | "clarification_needed" | "ineligible";
  eligibility_gaps?: string[];
  action_recommendation?: string | null;
  score_upper_bound?: number;
  job_grounding_coverage?: number;
  decision_reasons?: string[];
  id: string;
  candidate_id: string;
  job_id: string;
  overall_score: number;
  must_have_score: number;
  nice_to_have_score: number;
  recommendation: Recommendation;
  requirement_matches: RequirementMatch[];
  must_have_gaps_count: number;
  clarification_count?: number;
  citation_verification_score: number;
  citation_relevance_score?: number;
  evidence_coverage?: number;
  policy_version?: string;
  hitl_validated: boolean;
  recruiter_notes?: string | null;
  strictness?: number;
  job_snapshot?: JobDescription | null;
  created_at?: string;
  token_usage?: TokenUsageInfo | null;
  audit_metadata?: ActionAuditInfo | null;
}

export interface InterviewQuestion {
  id?: string;
  question_id?: string;
  target_requirement_id: string;
  archetype?: string;
  question_text: string;
  expected_answer?: string;
  expected_answers?: string[];
  expected_positive_signals?: string[];
  bad_answer?: string;
  bad_answers?: string[];
  red_flags?: string[];
  expected_answer_rubric?: string;
  difficulty?: "junior" | "mid" | "senior" | "principal" | string;
  rationale_for_asking?: string;
  estimated_minutes?: number;
  target_duration_minutes?: number;
}

export interface InterviewPlan {
  id: string;
  candidate_id: string;
  job_id: string;
  total_estimated_minutes?: number;
  total_duration_minutes: number;
  interview_focus_summary?: string;
  executive_summary: string;
  interviewer_tips?: string[];
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

export interface BatchFileProgress {
  id: string; document_id?: string | null; filename: string;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED" | "INTERRUPTED";
  phase: string; candidate_id?: string | null; error?: string | null; started_at?: string; finished_at?: string;
}

export interface BatchJobStatus {
  batch_id: string;
  job_id?: string | null;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "PARTIAL" | "FAILED" | "CANCELLED" | "INTERRUPTED";
  total_files: number;
  processed_files: number;
  failed_files: number;
  progress_percentage: number;
  results: BatchCandidateResult[];
  files?: BatchFileProgress[];
  currently_processing?: BatchFileProgress[];
  remaining_files?: number;
  queued_files?: number;
  concurrency_limit?: number;
  started_at?: string | null;
  finished_at?: string | null;
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
  parallel_screening_enabled?: boolean;
  cooldown_statuses?: Record<string, { provider: string; model: string; remaining_seconds: number; exhausted: boolean }>;
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

export interface DiscoveredLocalModel {
  id: string;
  name: string;
  provider: "ollama" | "lmstudio" | string;
  source: string;
  size_gb: number;
  parameter_size?: string;
  quantization?: string;
  format?: string;
  status: "running_in_vram" | "ready" | "installed" | string;
  is_running?: boolean;
  can_activate: boolean;
  full_path?: string;
  endpoint?: string;
}

export interface LocalModelScanResult {
  success: boolean;
  scanned_at: number;
  total_found: number;
  imported_count?: number;
  providers_detected: {
    ollama: {
      running: boolean;
      version?: string;
      models_count: number;
      models: DiscoveredLocalModel[];
    };
    lmstudio: {
      running: boolean;
      base_url?: string;
      live_models_count: number;
      disk_models_count: number;
      models: DiscoveredLocalModel[];
    };
    other_local_servers?: {
      count: number;
      models: DiscoveredLocalModel[];
    };
    filesystem_gguf?: {
      count: number;
      models: DiscoveredLocalModel[];
    };
  };
  all_models: DiscoveredLocalModel[];
  catalog_updated: boolean;
  message: string;
}

export interface RequirementComparisonCell {
  status: "met" | "partial" | "clarification_needed" | "not_met" | "not_evidenced";
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

export interface ActionAuditInfo {
  model_name: string;
  provider?: string | null;
  tokens_consumed: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  duration_ms: number;
  duration_seconds: number;
  initial_document_text_length: number;
  initial_document_word_count?: number;
  action_timestamp?: string | null;
}

export interface TokenUsageInfo {
  model_call_duration_ms?: number;
  model_calls?: number;
  models_used?: string[];
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

export interface JobRecommendationItem {
  rank: number;
  job_id: string;
  title: string;
  department?: string | null;
  location?: string | null;
  work_model?: string | null;
  employment_type?: string | null;
  seniority_level?: string | null;
  overall_score: number;
  must_have_score: number;
  nice_to_have_score: number;
  recommendation: Recommendation;
  must_have_gaps_count: number;
  total_requirements_count: number;
  matching_criteria_count: number;
  matching_skills: string[];
  key_strengths: string[];
  missing_requirements?: string[];
  justification?: string | null;
  has_full_evaluation: boolean;
  evaluation_id?: string | null;
}

export interface JobRecommendationResponse {
  candidate_id: string;
  candidate_name: string;
  total_database_jobs: number;
  recommendations: JobRecommendationItem[];
}

export interface ActionTraceLogEntry {
  id: string;
  timestamp: string | null;
  action_type: string;
  provider: string;
  model: string;
  status: string;
  latency_ms: number;
  tokens: { prompt: number; completion: number; total: number };
  prompt: string;
  system_prompt?: string | null;
  raw_response: string;
  parsed_json: any;
  error?: string | null;
  metadata?: Record<string, any>;
}

export interface ActionTraceResponse {
  export_metadata: {
    schema_version: string;
    generated_at: string;
    job_id?: string | null;
    job_title?: string | null;
    run_id?: string | null;
    total_actions: number;
    total_candidates: number;
    active_engine?: { provider: string; model: string; fallback_enabled: boolean };
    instruction_for_agent?: string;
  };
  job?: {
    id: string;
    title: string;
    department?: string | null;
    seniority_level?: string | null;
    location?: string | null;
    work_model?: string | null;
    employment_type?: string | null;
    source_url?: string | null;
    raw_text: string;
    requirements: Array<{
      id: string;
      title: string;
      category: string;
      weight: number;
      description: string;
      minimum_years_experience?: number | null;
    }>;
    custom_sections?: any[];
    unused_details?: string[];
  } | null;
  candidates?: Array<{
    candidate_id: string;
    candidate_name: string;
    original_filename?: string | null;
    raw_cv_text: string;
    sanitized_text: string;
    anonymized_profile: any;
    created_at?: string | null;
  }>;
  actions: ActionTraceLogEntry[];
  screening_run?: any;
}

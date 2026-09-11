"""
backend/agents/matching_agent.py
Semantic matching agent for evaluating candidate-JD alignment and gap proposals.
Retrieves candidate evidence chunks via ChromaDB and performs grounded LLM reasoning.
"""

from concurrent.futures import ThreadPoolExecutor
import logging
from typing import List, Optional
from uuid import UUID

from backend.agents.llm_factory import BaseLLMClient, get_llm_client
from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    RequirementMatch,
    VerbatimCitation,
)
from backend.services.scoring_engine import ScoringEngine
from backend.services.vector_store import VectorStoreService


MATCHING_SYSTEM_PROMPT = """You are an objective, evidence-driven HR Technical Evaluator.
Your responsibility is to determine if a candidate's background satisfies a specific Job Requirement.

Evaluation Principles:
1. Status Determination:
   - "met": Candidate has clear, demonstrated experience meeting the requirement. Score between 0.8 and 1.0.
   - "partial": Candidate has related or adjacent experience, or meets some but not all criteria. Score between 0.4 and 0.79.
   - "not_met": Evidence is missing, insufficient, or unrelated. Score between 0.0 and 0.39.
2. Verbatim Grounding (STRICT):
   - You MUST extract direct, exact verbatim substrings from the provided candidate evidence chunks.
   - Do not paraphrase or alter the quote. If no evidence exists, provide an empty citation list.
   - Set source_location to the role or section indicated in the evidence metadata (e.g., 'Lead AI Engineer at TechCorp' or 'Skills').
3. Rationale: Provide a concise (1-2 sentence) objective explanation justifying the match status based strictly on the cited evidence."""


class MatchingAgent:
    """Agent orchestrating retrieval, grounded LLM evaluation, and deterministic scoring."""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        vector_store: Optional[VectorStoreService] = None,
        scoring_engine: Optional[ScoringEngine] = None,
    ) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.vector_store = vector_store or VectorStoreService()
        self.scoring_engine = scoring_engine or ScoringEngine()

    def evaluate_requirement(
        self,
        candidate_id: UUID,
        requirement: JobRequirement,
        n_chunks: int = 3,
    ) -> RequirementMatch:
        """
        Retrieves top relevant candidate chunks for a single requirement and prompts LLM for grounded match.
        """
        # 1. Retrieve the most relevant candidate chunks from ChromaDB for this requirement
        retrieved_chunks = self.vector_store.query_candidate_chunks(
            candidate_id=candidate_id,
            query_text=requirement.description,
            n_results=n_chunks,
        )

        # 2. Format the retrieved evidence chunks with provenance metadata
        evidence_lines: List[str] = []
        for idx, chunk in enumerate(retrieved_chunks, start=1):
            meta = chunk.get("metadata", {})
            source = meta.get("job_title", "")
            if meta.get("company_name"):
                source += f" at {meta.get('company_name')}"
            if not source:
                source = meta.get("type", "Candidate Profile")
            evidence_lines.append(f"[Evidence {idx}] (Source: {source})\n\"{chunk.get('text', '')}\"")

        evidence_text = "\n\n".join(evidence_lines) if evidence_lines else "No directly matching evidence found in profile."

        # 3. Formulate the evaluation prompt
        prompt = (
            f"Job Requirement to Evaluate:\n"
            f"- ID: {requirement.id}\n"
            f"- Title: {requirement.title}\n"
            f"- Category: {requirement.category.value}\n"
            f"- Description: {requirement.description}\n"
            f"- Minimum Years Required: {requirement.minimum_years_experience or 'N/A'}\n\n"
            f"Candidate Profile Evidence Chunks:\n{evidence_text}\n\n"
            f"Evaluate whether the candidate meets this requirement. Respond ONLY with valid JSON conforming to the RequirementMatch schema.\n"
            f"Set requirement_id to '{requirement.id}'."
        )

        # 4. Invoke LLM structured generation
        match_result = self.llm_client.generate_structured(
            prompt=prompt,
            response_model=RequirementMatch,
            system_prompt=MATCHING_SYSTEM_PROMPT,
            temperature=0.0,
        )
        match_result.requirement_id = requirement.id
        return match_result

    def match_candidate(
        self,
        candidate: AnonymizedCandidate,
        job_description: JobDescription,
        n_chunks_per_req: int = 3,
    ) -> MatchEvaluationResult:
        """
        Full matching workflow:
        1. Indexes candidate chunks into ChromaDB (if not already indexed).
        2. Evaluates every requirement in the Job Description.
        3. Runs deterministic ScoringEngine verification and weighted calculation.
        """
        # 1. Ensure candidate is indexed in vector store
        self.vector_store.index_candidate(candidate)

        # 2. Evaluate all requirements in the JD concurrently
        matches: List[RequirementMatch] = []
        if job_description.requirements:
            def _evaluate_single(req: JobRequirement) -> RequirementMatch:
                try:
                    return self.evaluate_requirement(
                        candidate_id=candidate.candidate_id,
                        requirement=req,
                        n_chunks=n_chunks_per_req,
                    )
                except Exception as e:
                    logging.warning(f"Error evaluating requirement {req.id}: {e}")
                    return RequirementMatch(
                        requirement_id=req.id,
                        status=MatchStatus.NOT_MET,
                        score=0.0,
                        reasoning=f"Automated evaluation encountered a provider timeout or error: {str(e)}",
                        citations=[],
                    )

            max_workers = min(len(job_description.requirements), 6)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                matches = list(executor.map(_evaluate_single, job_description.requirements))

        # 3. Compute deterministic score, citation verification, and recommendation
        evaluation_result = self.scoring_engine.compute_evaluation(
            candidate=candidate,
            job=job_description,
            matches=matches,
        )

        return evaluation_result

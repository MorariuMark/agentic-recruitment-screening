"""
backend/services/batch_processor.py
Asynchronous batch processing service for high-volume CV parsing, anonymization,
vector indexing, and automated candidate-job requirement matching.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from backend.agents.matching_agent import MatchingAgent
from backend.agents.parser_agent import ParserAgent, ScannedPDFException
from backend.db.repository import DatabaseRepository
from backend.schemas.cv import AnonymizedCandidate, ParsedCV
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import MatchEvaluationResult
from backend.services.scoring_engine import ScoringEngine
from backend.services.vector_store import VectorStoreService

logger = logging.getLogger("recruitment_screening.batch_processor")


class BatchProcessorService:
    """Service orchestrating asynchronous batch screening of multiple candidate CVs."""

    def __init__(
        self,
        parser_agent: Optional[ParserAgent] = None,
        vector_store: Optional[VectorStoreService] = None,
        scoring_engine: Optional[ScoringEngine] = None,
        matching_agent: Optional[MatchingAgent] = None,
    ) -> None:
        self.parser_agent = parser_agent or ParserAgent()
        self.vector_store = vector_store or VectorStoreService()
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.matching_agent = matching_agent or MatchingAgent(
            vector_store=self.vector_store,
            scoring_engine=self.scoring_engine,
        )

    async def process_single_candidate(
        self,
        content_bytes: bytes,
        filename: str,
        job_description: Optional[JobDescription] = None,
    ) -> Dict[str, Any]:
        """
        Processes a single CV file: extracts structured profile, scrubs PII,
        indexes into ChromaDB, persists to relational database, and optionally
        evaluates against the specified Job Description.
        """
        try:
            # 1. Parse and scrub PII
            parsed_cv, anonymized_candidate = self.parser_agent.parse_and_anonymize(
                source=content_bytes,
                filename=filename,
            )

            # 2. Asymmetric RAG indexing in vector store
            chunks_indexed = self.vector_store.index_candidate(anonymized_candidate)

            # 3. Relational DB persistence
            await DatabaseRepository.save_candidate(
                parsed_cv=parsed_cv,
                anonymized_candidate=anonymized_candidate,
                chunks_indexed=chunks_indexed,
                filename=filename,
            )

            cid = anonymized_candidate.candidate_id
            result_item: Dict[str, Any] = {
                "candidate_id": str(cid),
                "filename": filename,
                "status": "COMPLETED",
                "chunks_indexed": chunks_indexed,
                "skills_count": len(parsed_cv.skills),
            }

            # 4. Optional automated matching against Job Description
            if job_description:
                try:
                    eval_result: MatchEvaluationResult = self.matching_agent.match_candidate(
                        candidate=anonymized_candidate,
                        job_description=job_description,
                    )
                    await DatabaseRepository.save_job(job_description)
                    await DatabaseRepository.save_evaluation(
                        eval_result=eval_result,
                        candidate_id=cid,
                        job_id=job_description.id,
                    )
                    result_item.update({
                        "evaluation_id": str(eval_result.id),
                        "overall_score": eval_result.overall_score,
                        "must_have_score": eval_result.must_have_score,
                        "nice_to_have_score": eval_result.nice_to_have_score,
                        "recommendation": eval_result.recommendation.value,
                        "must_have_gaps_count": eval_result.must_have_gaps_count,
                        "citation_verification_score": eval_result.citation_verification_score,
                    })
                except Exception as match_err:
                    logger.warning(f"Batch match evaluation failed for {filename}: {match_err}")
                    result_item["match_error"] = str(match_err)

            return result_item

        except ScannedPDFException as sc_err:
            logger.warning(f"Scanned PDF detected in batch processing for {filename}: {sc_err}")
            return {
                "filename": filename,
                "status": "FAILED",
                "error": f"Scanned or flat graphic document: {str(sc_err)}",
            }
        except Exception as e:
            logger.error(f"Failed processing candidate file {filename}: {e}", exc_info=True)
            return {
                "filename": filename,
                "status": "FAILED",
                "error": str(e),
            }

    async def execute_batch(
        self,
        batch_id: UUID,
        file_payloads: List[Tuple[str, bytes]],
        job_id: Optional[UUID] = None,
    ) -> None:
        """
        Executes screening across all files in a batch asynchronously,
        updating database progress as each candidate completes.
        """
        job_description: Optional[JobDescription] = None
        if job_id:
            job_record = await DatabaseRepository.get_job(job_id)
            if job_record:
                reqs = [
                    JobRequirement(
                        id=r.id,
                        title=r.title,
                        category=RequirementCategory(r.category),
                        weight=r.weight,
                        description=r.description,
                        minimum_years_experience=r.minimum_years_experience,
                    )
                    for r in (job_record.requirements or [])
                ]
                job_description = JobDescription(
                    id=UUID(job_record.id),
                    title=job_record.title,
                    department=job_record.department,
                    seniority_level=job_record.seniority_level,
                    location=job_record.location,
                    work_model=job_record.work_model,
                    employment_type=job_record.employment_type,
                    requirements=reqs,
                )

        logger.info(f"Starting batch {batch_id} with {len(file_payloads)} files (job_id={job_id}).")

        for idx, (filename, content_bytes) in enumerate(file_payloads, start=1):
            logger.info(f"Batch {batch_id}: processing file {idx}/{len(file_payloads)} ({filename})...")
            result_item = await self.process_single_candidate(
                content_bytes=content_bytes,
                filename=filename,
                job_description=job_description,
            )
            is_success = (result_item.get("status") == "COMPLETED")
            is_completed = (idx == len(file_payloads))

            await DatabaseRepository.update_batch_progress(
                batch_id=batch_id,
                candidate_result=result_item,
                is_success=is_success,
                is_completed=is_completed,
            )

        logger.info(f"Batch {batch_id} processing complete.")

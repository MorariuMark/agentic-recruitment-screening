"""
backend/services/batch_processor.py
Asynchronous batch processing service for high-volume CV parsing, anonymization,
vector indexing, and automated candidate-job requirement matching.
"""

import asyncio
import logging
import time
from contextvars import ContextVar
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from backend.agents.matching_agent import MatchingAgent
from backend.agents.parser_agent import ParserAgent, ScannedPDFException
from backend.agents.llm_factory import LLMProvidersCoolingDownError
from backend.config import settings
from backend.db.repository import DatabaseRepository
from backend.schemas.cv import AnonymizedCandidate, ParsedCV
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import MatchEvaluationResult
from backend.services.event_stream import event_broadcaster
from backend.services.operation_timing import record_operation, measure
from backend.services.scoring_engine import ScoringEngine
from backend.services.vector_store import VectorStoreService

logger = logging.getLogger("recruitment_screening.batch_processor")

# Global admission semaphore bounding concurrent parsing across all batches (E10)
GLOBAL_PARSER_SEMAPHORE = asyncio.Semaphore(4)
_file_phase = ContextVar("cv_file_phase", default=None)


async def report_file_phase(phase):
    callback = _file_phase.get()
    if callback:
        await callback(phase)


async def _provider_delay(seconds):
    await asyncio.sleep(seconds)


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

    @record_operation(lambda a: "cv_processing" if a["job_description"] else "cv_parse",
                      lambda a: {"label": a["filename"], "job_id": a["job_description"].id if a["job_description"] else None})
    async def process_single_candidate(self, content_bytes, filename, job_description=None):
        from backend.services.cv_library import ingestion_gate, store_file, attach_candidate
        async with ingestion_gate.parsing(content_bytes):
            document, duplicate = await store_file(filename, content_bytes)
            if document.deleted_at:
                return {"filename": filename, "status": "FAILED", "error": "This exact CV is in Trash. Restore it first."}
            if document.candidate_id:
                return {"filename": filename, "candidate_id": document.candidate_id, "status": "COMPLETED", "duplicate_removed": True}
            result = await self._process_single_candidate(content_bytes, filename, job_description)
            if result.get("candidate_id"):
                await attach_candidate(document.id, result["candidate_id"])
            return result

    async def _process_single_candidate(
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
            await report_file_phase("Parsing and anonymizing CV")
            # 1. Parse and scrub PII
            parsed_cv, anonymized_candidate = await asyncio.to_thread(self.parser_agent.parse_and_anonymize,
                source=content_bytes,
                filename=filename,
            )

            await report_file_phase("Indexing CV evidence")
            # 2. Asymmetric RAG indexing in vector store
            chunks_indexed = await asyncio.to_thread(self.vector_store.index_candidate, anonymized_candidate)

            await report_file_phase("Saving parsed profile")
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
                    async with measure("candidate_screening", candidate_id=str(anonymized_candidate.candidate_id), job_id=str(job_description.id)):
                        eval_result: MatchEvaluationResult = await asyncio.to_thread(self.matching_agent.match_candidate,
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

        except LLMProvidersCoolingDownError:
            raise
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

    @record_operation("batch_parse", lambda a: {"batch_id": a["batch_id"], "item_count": len(a["file_payloads"]), "label": f"Parse batch of {len(a['file_payloads'])} CVs"})
    async def execute_parse_batch(self, batch_id: UUID, file_payloads: List[Tuple[str, bytes]], concurrency=4, document_ids=None) -> None:
        """Parse a bounded queue with durable, per-file lifecycle updates."""
        record = await DatabaseRepository.get_batch_job(batch_id)
        # A batch is a single session. Re-delivery must never replay finished work.
        if not record or record.status not in {"PROCESSING", "QUEUED"}:
            return
        concurrency = max(1, min(int(concurrency), 4))
        if document_ids is None:
            # Persist every original before the first provider call. An outage
            # must not strand the unstarted queue in transient request memory.
            from backend.services.cv_library import store_file
            document_ids = [(await store_file(name, content))[0].id for name, content in file_payloads]
        await DatabaseRepository.initialize_batch_files(batch_id, [name for name, _ in file_payloads], concurrency, document_ids)
        record = await DatabaseRepository.get_batch_job(batch_id)
        if not record or record.status not in {"PROCESSING", "QUEUED"}:
            return
        finished_ids = {str(item.get("file_id")) for item in (record.results_json or []) if item.get("file_id") is not None}
        finished_ids.update(str(item["id"]) for item in (record.progress_json or {}).get("files", [])
                            if item["status"] not in {"PROCESSING", "QUEUED"})
        queue = asyncio.Queue()
        for index, (name, content) in enumerate(file_payloads):
            if str(index) not in finished_ids:
                queue.put_nowait((str(index), name, content))
        progress_lock = asyncio.Lock()
        outage_deadline = None

        async def worker():
            nonlocal outage_deadline
            processor = None
            while not queue.empty():
                file_id, filename, content = queue.get_nowait()
                async def phase(label):
                    async with progress_lock:
                        await DatabaseRepository.update_batch_file(batch_id, file_id, label)
                token = _file_phase.set(phase)
                try:
                    while True:
                        try:
                            async with GLOBAL_PARSER_SEMAPHORE:
                                await phase("Parsing and anonymizing CV")
                                if processor is None:
                                    processor = BatchProcessorService(parser_agent=ParserAgent(), vector_store=self.vector_store)
                                result = await processor.process_single_candidate(content, filename)
                            outage_deadline = None
                            break
                        except LLMProvidersCoolingDownError as error:
                            if outage_deadline is None:
                                outage_deadline = time.monotonic() + settings.parser_provider_wait_seconds
                            remaining = outage_deadline - time.monotonic()
                            if remaining <= 0:
                                raise
                            delay = min(error.retry_after, 30, remaining)
                            await phase(f"Waiting for AI providers; retrying this CV in {delay:.0f}s")
                            # Release the global parser slot while waiting; cancellation remains available.
                            await _provider_delay(delay)
                    result = {**result, "file_id": file_id}
                    async with progress_lock:
                        await DatabaseRepository.update_batch_progress(batch_id, result, is_success=result.get("status") == "COMPLETED")
                except asyncio.CancelledError:
                    raise
                except LLMProvidersCoolingDownError:
                    raise
                except Exception as error:
                    async with progress_lock:
                        await DatabaseRepository.update_batch_progress(batch_id,
                            {"file_id": file_id, "filename": filename, "status": "FAILED", "error": str(error)}, is_success=False)
                finally:
                    _file_phase.reset(token)
                    queue.task_done()

        tasks = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(file_payloads)))]
        try:
            await asyncio.gather(*tasks)
        except BaseException as error:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if isinstance(error, LLMProvidersCoolingDownError):
                await DatabaseRepository.finish_batch_files(batch_id, "INTERRUPTED",
                    "AI providers are temporarily unavailable. Completed profiles are retained; remaining CVs were not failed. Retry the unparsed CVs from the library.")
                return
            await DatabaseRepository.finish_batch_files(batch_id, "CANCELLED" if isinstance(error, asyncio.CancelledError) else "FAILED",
                                                       "Cancelled before completion" if isinstance(error, asyncio.CancelledError) else str(error))
            raise

    @record_operation("batch_screening", lambda a: {"batch_id": a["batch_id"], "job_id": a["job_id"], "item_count": len(a["file_payloads"])})
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
        from backend.services.cv_library import store_file
        for name, content in file_payloads:
            await store_file(name, content)
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
        await event_broadcaster.publish_batch_event(
            batch_id=batch_id,
            event_type="batch_started",
            data={
                "batch_id": str(batch_id),
                "total_files": len(file_payloads),
                "job_id": str(job_id) if job_id else None,
            },
        )

        try:
            for idx, (filename, content_bytes) in enumerate(file_payloads, start=1):
                logger.info(f"Batch {batch_id}: processing file {idx}/{len(file_payloads)} ({filename})...")
                await event_broadcaster.publish_batch_event(
                    batch_id=batch_id,
                    event_type="file_processing",
                    data={
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "current_index": idx,
                        "total_files": len(file_payloads),
                    },
                )

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

                progress_pct = round((idx / len(file_payloads)) * 100.0, 1)
                await event_broadcaster.publish_batch_event(
                    batch_id=batch_id,
                    event_type="file_completed",
                    data={
                        "batch_id": str(batch_id),
                        "filename": filename,
                        "result": result_item,
                        "processed_count": idx,
                        "total_files": len(file_payloads),
                        "progress_percentage": progress_pct,
                    },
                )

            logger.info(f"Batch {batch_id} processing complete.")
            await event_broadcaster.publish_batch_event(
                batch_id=batch_id,
                event_type="batch_completed",
                data={
                    "batch_id": str(batch_id),
                    "status": "COMPLETED",
                    "total_files": len(file_payloads),
                },
            )
        except LLMProvidersCoolingDownError:
            await DatabaseRepository.finish_batch_files(batch_id, "INTERRUPTED",
                "AI providers are temporarily unavailable. Completed profiles are retained; retry remaining unparsed CVs from the library.")
        except Exception as batch_err:
            logger.error(f"Catastrophic failure in batch {batch_id}: {batch_err}", exc_info=True)
            await event_broadcaster.publish_batch_event(
                batch_id=batch_id,
                event_type="batch_failed",
                data={
                    "batch_id": str(batch_id),
                    "status": "FAILED",
                    "error": str(batch_err),
                    "total_files": len(file_payloads),
                },
            )

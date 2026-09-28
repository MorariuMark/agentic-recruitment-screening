"""
tests/test_database.py
Comprehensive test suite for SQLAlchemy relational models and async repository layer.
Verifies table creation, CRUD operations, relationships, and audit trail persistence.
"""

from pathlib import Path
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from backend.db.models import Base
from backend.db.repository import DatabaseRepository
from backend.schemas.cv import (
    AnonymizedCandidate,
    ContactInfo,
    Education,
    LanguageSkill,
    ParsedCV,
    Project,
    WorkExperience,
)
from backend.schemas.interview import InterviewPlan, InterviewQuestion, QuestionArchetype
from backend.schemas.job import JobDescription, JobRequirement, RequirementCategory
from backend.schemas.match import (
    MatchEvaluationResult,
    MatchStatus,
    Recommendation,
    RequirementMatch,
    VerbatimCitation,
)

TEST_DB_FILE = "./data/test_db_verification.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"


@pytest_asyncio.fixture(scope="module")
async def test_engine():
    """Sets up an isolated test database engine and tables."""
    # Ensure data folder exists
    Path("./data").mkdir(parents=True, exist_ok=True)
    if Path(TEST_DB_FILE).exists():
        Path(TEST_DB_FILE).unlink()

    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    if Path(TEST_DB_FILE).exists():
        try:
            Path(TEST_DB_FILE).unlink()
        except Exception:
            pass


@pytest_asyncio.fixture
async def db_session(test_engine):
    """Provides a transactional database session for each test."""
    factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.mark.asyncio
async def test_job_and_requirements_persistence(db_session):
    """Verify JobDescription and decomposed atomic requirements persist and retrieve properly."""
    jid = uuid4()
    job = JobDescription(
        id=jid,
        title="Senior AI Platform Lead",
        department="Core AI Systems",
        seniority_level="Senior",
        requirements=[
            JobRequirement(
                id="req_python_fastapi",
                title="Python & FastAPI",
                category=RequirementCategory.MUST_HAVE,
                weight=1.0,
                description="Production API design with FastAPI.",
                minimum_years_experience=3,
            ),
            JobRequirement(
                id="req_k8s",
                title="Kubernetes",
                category=RequirementCategory.NICE_TO_HAVE,
                weight=0.8,
                description="Cluster orchestration.",
                minimum_years_experience=2,
            ),
        ],
    )

    saved_job = await DatabaseRepository.save_job(
        job=job,
        source_url="https://example.com/careers/ai-lead",
        raw_text="Job posting text here...",
        session=db_session,
    )
    assert saved_job.id == str(jid)
    assert saved_job.title == "Senior AI Platform Lead"
    assert len(saved_job.requirements) == 2

    # Retrieve
    fetched = await DatabaseRepository.get_job(jid, session=db_session)
    assert fetched is not None
    assert fetched.title == "Senior AI Platform Lead"
    assert len(fetched.requirements) == 2
    assert fetched.requirements[0].id == "req_python_fastapi"
    assert fetched.requirements[0].weight == 1.0


@pytest.mark.asyncio
async def test_candidate_persistence(db_session):
    """Verify ParsedCV and AnonymizedCandidate persist to the database."""
    cid = uuid4()
    raw_cv = ParsedCV(
        contact_info=ContactInfo(
            full_name="Jane Doe",
            email="jane@example.com",
            location="Berlin, Germany",
        ),
        skills=["Python", "FastAPI", "Docker", "PyTorch"],
        experiences=[
            WorkExperience(
                job_title="Senior AI Engineer",
                company_name="CloudTech",
                work_description=["Architected real-time RAG inference services with FastAPI."],
                skills_used=["Python", "FastAPI"],
            )
        ],
    )
    anonymized = AnonymizedCandidate(
        candidate_id=cid,
        anonymized_work_experiences=raw_cv.experiences,
        anonymized_skills=raw_cv.skills,
        sanitized_text="[CANDIDATE_NAME] at CloudTech architected real-time RAG inference services with FastAPI.",
        demographic_data={"location": "Berlin, Germany"},
    )

    saved = await DatabaseRepository.save_candidate(
        parsed_cv=raw_cv,
        anonymized_candidate=anonymized,
        chunks_indexed=4,
        filename="Jane_Doe_CV.pdf",
        session=db_session,
    )
    assert saved.id == str(cid)
    assert saved.chunks_indexed == 4
    assert saved.original_filename == "Jane_Doe_CV.pdf"

    # Fetch
    fetched = await DatabaseRepository.get_candidate(cid, session=db_session)
    assert fetched is not None
    assert fetched.id == str(cid)
    assert fetched.raw_cv_json["skills"] == ["Python", "FastAPI", "Docker", "PyTorch"]
    assert "FastAPI" in fetched.sanitized_text

    # List
    all_cands = await DatabaseRepository.list_candidates(session=db_session)
    assert any(c.id == str(cid) for c in all_cands)


@pytest.mark.asyncio
async def test_evaluation_and_hitl_persistence(db_session):
    """Verify MatchEvaluationResult, citations, and HITL overrides persist."""
    cid = uuid4()
    jid = uuid4()
    eid = uuid4()

    # Create dummy candidate and job first to satisfy FK
    await DatabaseRepository.save_candidate(
        parsed_cv=ParsedCV(contact_info=ContactInfo(full_name="Python Dev"), skills=["Python"]),
        anonymized_candidate=AnonymizedCandidate(
            candidate_id=cid,
            anonymized_skills=["Python"],
            sanitized_text="Python engineer",
        ),
        session=db_session,
    )
    await DatabaseRepository.save_job(
        job=JobDescription(id=jid, title="Backend Dev", requirements=[]),
        session=db_session,
    )

    eval_result = MatchEvaluationResult(
        id=eid,
        candidate_id=cid,
        job_id=jid,
        overall_score=88.5,
        must_have_score=90.0,
        nice_to_have_score=84.0,
        must_have_gaps_count=0,
        recommendation=Recommendation.STRONG_MATCH,
        citation_verification_score=1.0,
        requirement_matches=[
            RequirementMatch(
                requirement_id="req_python_fastapi",
                status=MatchStatus.MET,
                score=0.95,
                confidence=0.95,
                reasoning="Demonstrated 4 years FastAPI microservices.",
                citations=[
                    VerbatimCitation(
                        quote="Architected real-time RAG inference services with FastAPI.",
                        source_section="Senior AI Engineer at CloudTech",
                        verified=True,
                    )
                ],
            )
        ],
    )

    saved_eval = await DatabaseRepository.save_evaluation(
        eval_result=eval_result,
        candidate_id=cid,
        job_id=jid,
        session=db_session,
    )
    assert saved_eval.id == str(eid)
    assert saved_eval.overall_score == 88.5
    assert saved_eval.hitl_validated is False

    # Perform HITL validation override
    updated = await DatabaseRepository.update_hitl_validation(
        evaluation_id=eid,
        decision="BORDERLINE",
        notes="Candidate has strong API skills but lacks cloud orchestration depth.",
        session=db_session,
    )
    assert updated is not None
    assert updated.hitl_validated is True
    assert updated.recommendation == "BORDERLINE"
    assert "orchestration" in updated.recruiter_notes

    # Verify query for job evaluations
    job_evals = await DatabaseRepository.list_evaluations_for_job(jid, session=db_session)
    assert len(job_evals) == 1
    assert job_evals[0].id == str(eid)


@pytest.mark.asyncio
async def test_interview_plan_and_audit_log(db_session):
    """Verify InterviewPlan and AuditLog persist correctly."""
    cid = uuid4()
    jid = uuid4()
    pid = uuid4()

    # Pre-seed candidate and job
    await DatabaseRepository.save_candidate(
        parsed_cv=ParsedCV(contact_info=ContactInfo(full_name="Python Dev"), skills=["Python"]),
        anonymized_candidate=AnonymizedCandidate(
            candidate_id=cid,
            anonymized_skills=["Python"],
            sanitized_text="Python engineer",
        ),
        session=db_session,
    )
    await DatabaseRepository.save_job(
        job=JobDescription(id=jid, title="Platform Lead", requirements=[]),
        session=db_session,
    )

    plan = InterviewPlan(
        id=pid,
        candidate_id=cid,
        job_id=jid,
        total_estimated_minutes=45,
        questions=[
            InterviewQuestion(
                id="q1",
                archetype=QuestionArchetype.TECHNICAL_DEEP_DIVE,
                target_requirement_id="req_python_fastapi",
                question_text="How do you handle connection pooling and async timeouts in FastAPI under high load?",
                allocated_minutes=15,
                expected_positive_signals=["Mentions uvloop, asyncpg, and graceful connection shedding."],
                red_flags=["Blocking calls inside async def endpoints."],
            )
        ],
    )

    saved_plan = await DatabaseRepository.save_interview_plan(
        plan=plan,
        session=db_session,
    )
    assert saved_plan.id == str(pid)
    assert saved_plan.total_estimated_minutes == 45

    fetched_plan = await DatabaseRepository.get_interview_plan(pid, session=db_session)
    assert fetched_plan is not None
    assert len(fetched_plan.questions_json) == 1
    assert fetched_plan.questions_json[0]["id"] == "q1"

    # Audit log test
    audit_entry = await DatabaseRepository.record_audit_log(
        entity_type="candidate",
        entity_id=str(cid),
        action="PII_SCRUBBED",
        details={"redacted_fields": ["name", "email", "phone"]},
        session=db_session,
    )
    assert audit_entry.id is not None
    assert audit_entry.action == "PII_SCRUBBED"

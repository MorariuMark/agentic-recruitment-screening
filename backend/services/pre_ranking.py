"""One embedding batch and one matrix product; no generative LLM calls."""
import re
from datetime import date, datetime

import numpy as np

from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription
from backend.schemas.screening import PreScreenRow
from backend.services.skill_equivalence import EQUIVALENCE_CLUSTERS, SkillEquivalenceService
from backend.services.evidence import assess_language, clean_model_text, language_priority


def contains(text: str, term: str) -> bool:
    return bool(re.search(r"(?<![\w+#])" + re.escape(term.lower()) + r"(?![\w+#])", text.lower()))


VOCABULARY = {term for group in EQUIVALENCE_CLUSTERS for term in group["members"]} | {
    "python", "java", "javascript", "typescript", "c++", "c#", "sql", "excel",
    "linux", "windows", "git", "html", "css", "sap", "power bi", "pandas", "pytorch",
}
STOP_WORDS = set("experience experienced expertise proficiency proficient knowledge working strong required minimum years year of in with and or the a an ability skills skill development programming professional relevant overall total proven language languages".split())


def requirement_terms(title: str, description: str) -> list[str]:
    text = f"{title} {description}".lower()
    terms = sorted(term for term in VOCABULARY if contains(text, term))
    # Avoid counting nested names twice (SQL inside SQL Server, for example).
    terms = [term for term in terms if not any(term != other and contains(other, term) for other in terms)]
    return terms or [t for t in re.findall(r"[\w+#.-]+", title.lower()) if t not in STOP_WORDS and not t.isdigit()]


from backend.services.tenure_calculator import TenureCalculator, month_index


def experience_years(candidate: AnonymizedCandidate, terms: list[str]) -> float:
    """Union dated months to avoid double-counting overlapping jobs; never invent tenure."""
    return TenureCalculator.calculate_experience_years(candidate, terms)


class PreRankingEngine:
    WEIGHTS = {"similarity_score": .40, "skills_score": .30, "experience_score": .20, "degree_score": .10}

    def __init__(self, embedding_fn):
        self.embedding_fn = embedding_fn

    def rank(self, candidates: list[AnonymizedCandidate], job: JobDescription) -> list[PreScreenRow]:
        if not candidates:
            return []
        # Structured, job-relevant data only: exclude names, contacts and demographics.
        profiles = []
        for candidate in candidates:
            profiles.append(" ".join([
                *candidate.anonymized_skills,
                *[" ".join([r.job_title, *r.skills_used, *r.work_description]) for r in candidate.anonymized_work_experiences],
                *[f"{e.degree_title} {e.field_of_study or ''}" for e in candidate.anonymized_education],
                *[" ".join([p.project_name, *p.description, *p.technologies]) for p in candidate.anonymized_projects],
                *candidate.anonymized_certifications,
                *[f"{language.language} {language.proficiency or ''}" for language in candidate.anonymized_languages],
                *[publication.title for publication in candidate.anonymized_publications],
                *[patent.title for patent in candidate.anonymized_patents],
                *[" ".join([section.section_title, *section.items]) for section in candidate.anonymized_custom_sections if section.is_relevant],
            ]) or "No documented professional evidence")
        profiles = [clean_model_text(profile) for profile in profiles]
        job_text = " ".join([job.title, *[f"{r.title}: {r.description}" for r in job.requirements if r.weight > 0]])
        vectors = np.asarray(self.embedding_fn([job_text, *profiles]), dtype=float)
        if vectors.ndim != 2 or vectors.shape[0] != len(candidates) + 1 or not np.isfinite(vectors).all():
            raise ValueError("Embedding service returned invalid vectors")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized = np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms > 0)
        similarities = np.clip(normalized[1:] @ normalized[0], 0, 1) * 100
        rows = []
        for candidate, profile, similarity in zip(candidates, profiles, similarities):
            buckets: dict[str, list[tuple[float, float]]] = {"skills_score": [], "experience_score": [], "degree_score": []}
            checks = []
            for requirement in job.requirements:
                if requirement.category != "must_have" or requirement.weight <= 0:
                    continue
                text = f"{requirement.title} {requirement.description}"
                is_degree = bool(re.search(r"\b(degree|bachelor|master|phd|diploma|bsc|msc|university)\b", text, re.I))
                if is_degree:
                    evidence = SkillEquivalenceService.evaluate_degree_hierarchy(candidate.anonymized_education, requirement.title, requirement.description)
                    passed = bool(evidence and evidence[0])
                    buckets["degree_score"].append((float(passed), requirement.weight))
                    checks.append(f"{requirement.title}: {'documented qualification matches' if passed else 'qualification not verified from CV'}")
                    continue
                language_evidence = assess_language(candidate, requirement)
                if language_evidence is not None:
                    buckets["skills_score"].append((language_evidence[1] / 100, requirement.weight))
                    checks.append(f"{requirement.title}: {language_evidence[0]}. {language_evidence[2]}")
                    continue
                terms = requirement_terms(requirement.title, requirement.description)
                if terms:
                    found = [term for term in terms if contains(profile, term)]
                    buckets["skills_score"].append((len(found) / len(terms), requirement.weight))
                    checks.append(f"{requirement.title}: {len(found)}/{len(terms)} skill terms documented ({', '.join(found) or 'none'})")
                years = requirement.minimum_years_experience
                if years is None:
                    match = re.search(r"(\d+)\s*\+?\s*years?", text, re.I)
                    years = int(match.group(1)) if match else None
                if years and years > 0:
                    actual = experience_years(candidate, terms)
                    buckets["experience_score"].append((min(actual / years, 1), requirement.weight))
                    checks.append(f"{requirement.title}: {actual:.1f}/{years} years documented; missing dates need review")
            scores = {key: (100 * sum(v * w for v, w in values) / sum(w for _, w in values)) if values else None for key, values in buckets.items()}
            scores["similarity_score"] = float(similarity)
            active_weight = sum(self.WEIGHTS[k] for k, v in scores.items() if v is not None)
            composite = sum(self.WEIGHTS[k] * v for k, v in scores.items() if v is not None) / active_weight
            rows.append(PreScreenRow(candidate_id=candidate.candidate_id, pre_screen_score=round(composite, 2), checks=checks, **{k: round(v, 2) if v is not None else None for k, v in scores.items()}))
        priorities = {str(c.candidate_id): language_priority(c, job) for c in candidates}
        for row in rows:
            row.language_priority = priorities[str(row.candidate_id)]
        rows.sort(key=lambda row: (row.language_priority, -row.pre_screen_score, str(row.candidate_id)))
        for rank, row in enumerate(rows, 1):
            row.rank = rank
        return rows

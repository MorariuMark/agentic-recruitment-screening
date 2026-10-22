"""Requirement-level evidence retrieval and scoring. No generative model calls."""
from collections import Counter
import hashlib
import json
import math
import re
import time

import numpy as np

from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription
from backend.schemas.screening import EvidencePassage, PreScreenRow, RequirementAssessment
from backend.services.pre_ranking import contains, month_index, requirement_terms, STOP_WORDS
from backend.services.skill_equivalence import CEFR_LEVELS, SkillEquivalenceService
from backend.services.evidence import assess_language, clean_model_text, language_priority

VERSION = "evidence-v2.3"
ALIASES = {"postgres": "postgresql", "js": "javascript", "ts": "typescript", "k8s": "kubernetes", "node.js": "nodejs", "csharp": "c#"}


def tokens(text):
    return [ALIASES.get(t, t) for t in re.findall(r"[\w+#.]+", text.casefold()) if t not in STOP_WORDS]


def term_matches(text, term):
    return contains(text, term) or ALIASES.get(term, term) in set(tokens(text))


def language_assessment(candidate, requirement):
    return assess_language(candidate, requirement)


def evidence_units(candidate: AnonymizedCandidate) -> list[EvidencePassage]:
    """Bound inference input while retaining the full source in the candidate record."""
    units = []
    def add(section, text, strength="demonstrated"):
        text = clean_model_text(" ".join(text.split()))
        # Reserve space for qualifications/languages even when one role is very long.
        for offset in list(range(0, len(text), 900))[:4]:
            excerpt = text[offset:offset + 1000]
            if not excerpt or len(units) >= 40:
                return
            key = hashlib.sha256(f"{section}:{offset}:{excerpt}".encode()).hexdigest()[:20]
            if not any(unit.id == key for unit in units):
                units.append(EvidencePassage(id=key, section=section, text=excerpt, strength=strength))
    for i, education in enumerate(candidate.anonymized_education):
        add(f"education[{i}]", f"{education.degree_title} {education.field_of_study or ''}")
    for i, language in enumerate(candidate.anonymized_languages):
        add(f"languages[{i}]", f"{language.language} {language.proficiency or ''}")
    for i, certification in enumerate(candidate.anonymized_certifications):
        add(f"certifications[{i}]", certification)
    add("skills", " ".join(candidate.anonymized_skills), "listed")
    for i, role in enumerate(candidate.anonymized_work_experiences):
        add(f"experience[{i}]", " ".join([role.job_title, *role.work_description, *role.skills_used]))
    for i, project in enumerate(candidate.anonymized_projects):
        add(f"projects[{i}]", " ".join([project.project_name, *project.description, *project.technologies]))
    for i, section in enumerate(candidate.anonymized_custom_sections):
        if section.is_relevant:
            add(f"additional[{i}]", " ".join([section.section_title, *section.items]), "listed")
    for i, publication in enumerate(candidate.anonymized_publications):
        add(f"publications[{i}]", publication.title)
    for i, patent in enumerate(candidate.anonymized_patents):
        add(f"patents[{i}]", patent.title)
    return units


def feature_key(candidate, model_key):
    units = [unit.model_dump() for unit in evidence_units(candidate)]
    return hashlib.sha256(json.dumps([VERSION, model_key, units], sort_keys=True).encode()).hexdigest()


def snapshot_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def relevant_years(candidate, terms, req_text=""):
    from backend.services.tenure_calculator import TenureCalculator
    return TenureCalculator.calculate_requirement_tenure(candidate, terms, req_text)


class HybridRankingEngine:
    def __init__(self, embedding_fn, model_key="default", feature_cache=None):
        self.embedding_fn = embedding_fn
        self.model_key = model_key
        self.feature_cache = feature_cache or {}
        self.cache_updates = {}
        self.diagnostics = {"version": VERSION, "cache_hits": 0, "cache_misses": 0, "warnings": [], "timings_ms": {}}

    def rank(self, candidates, job: JobDescription, evidence_limit=3):
        started = time.perf_counter()
        requirements = [r for r in job.requirements if r.weight > 0]
        if not requirements:
            raise ValueError("Add at least one weighted requirement before improved screening.")
        if len(requirements) > 100:
            raise ValueError("Improved screening supports up to 100 weighted requirements per job.")
        query_texts = [f"{r.title}: {r.description}" for r in requirements] or [job.title]
        prepared = [(candidate, evidence_units(candidate)) for candidate in candidates]
        corpus, owners, vectors = [], [], []
        owner_indices = {}
        missing_texts, missing_slots = [], []
        for candidate, units in prepared:
            key = feature_key(candidate, self.model_key)
            cached = self.feature_cache.get(key, {})
            cached_vectors = cached.get("vectors", [])
            valid = len(cached_vectors) == len(units) and bool(units)
            self.diagnostics["cache_hits" if valid else "cache_misses"] += 1
            for index, unit in enumerate(units):
                slot = len(corpus)
                corpus.append(unit)
                owners.append(str(candidate.candidate_id))
                owner_indices.setdefault(str(candidate.candidate_id), []).append(slot)
                vectors.append(cached_vectors[index] if valid else None)
                if not valid:
                    missing_texts.append(unit.text)
                    missing_slots.append(slot)
            if len(units) == 40:
                self.diagnostics["warnings"].append(f"Evidence limit reached for candidate {candidate.candidate_id}; full CV remains available.")
        texts = [*query_texts, *missing_texts]
        encoded = []
        for offset in range(0, len(texts), 128):
            batch = np.asarray(self.embedding_fn(texts[offset:offset + 128]), dtype=float)
            if batch.ndim != 2 or len(batch) != len(texts[offset:offset + 128]) or not np.isfinite(batch).all():
                raise ValueError("Embedding service returned invalid evidence vectors")
            encoded.extend(batch.tolist())
        queries = np.asarray(encoded[:len(query_texts)], dtype=float)
        for slot, vector in zip(missing_slots, encoded[len(query_texts):]):
            vectors[slot] = vector
        matrix = np.asarray(vectors, dtype=float) if vectors else np.empty((0, queries.shape[1]))
        if matrix.ndim != 2 or matrix.shape[1] != queries.shape[1] or not np.isfinite(matrix).all():
            raise ValueError("Cached evidence vectors do not match the embedding model; rebuild the cache.")
        for candidate, units in prepared:
            indices = owner_indices.get(str(candidate.candidate_id), [])
            if units:
                self.cache_updates[feature_key(candidate, self.model_key)] = {"vectors": [vectors[i] for i in indices], "version": VERSION}
        norm = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = np.divide(matrix, norm, out=np.zeros_like(matrix), where=norm > 0)
        norm = np.linalg.norm(queries, axis=1, keepdims=True)
        queries = np.divide(queries, norm, out=np.zeros_like(queries), where=norm > 0)
        similarities = np.clip(matrix @ queries.T, -1, 1)
        documents = [Counter(tokens(unit.text)) for unit in corpus]
        lengths = np.array([sum(document.values()) for document in documents])
        average_length = float(np.mean(lengths)) if len(lengths) else 1
        frequencies = Counter(term for document in documents for term in document)
        lexical = []
        for query in query_texts:
            scores = np.zeros(len(corpus))
            for term in set(tokens(query)):
                frequency = np.array([document.get(term, 0) for document in documents])
                idf = math.log(1 + (len(corpus) - frequencies[term] + .5) / (frequencies[term] + .5))
                scores += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * lengths / max(average_length, 1)))
            lexical.append(scores)
        self.diagnostics["timings_ms"]["evidence_and_retrieval"] = round((time.perf_counter() - started) * 1000, 2)
        rows = []
        for candidate, units in prepared:
            indices = owner_indices.get(str(candidate.candidate_id), [])
            assessments = []
            for q, requirement in enumerate(requirements):
                dense_order = sorted(indices, key=lambda i: (-similarities[i, q], corpus[i].id))
                lexical_order = sorted([i for i in indices if lexical[q][i] > 0], key=lambda i: (-lexical[q][i], corpus[i].id))
                fusion = Counter()
                for ranking in [dense_order, lexical_order]:
                    for position, i in enumerate(ranking, 1):
                        fusion[i] += 1 / (60 + position)
                best = sorted(indices, key=lambda i: (-fusion[i], corpus[i].id))[:evidence_limit]
                similarity = max([float(similarities[i, q]) for i in best], default=0)
                assessments.append(self.assess(candidate, requirement, [corpus[i] for i in best], similarity,
                    {corpus[i].id: float(similarities[i, q]) for i in best}))
            active = [a for a in assessments if a.category != "soft_skill"]
            total_weight = sum(a.weight for a in active)
            score = sum(a.score * a.weight for a in active) / total_weight if total_weight else 0
            required = [a for a in assessments if a.category == "must_have"]
            preferred = [a for a in assessments if a.category == "nice_to_have"]
            if required and preferred:
                score = .8 * sum(a.score * a.weight for a in required) / sum(a.weight for a in required) + .2 * sum(a.score * a.weight for a in preferred) / sum(a.weight for a in preferred)
            rows.append(PreScreenRow(candidate_id=candidate.candidate_id, pre_screen_score=round(score, 2),
                similarity_score=round(max(0, max([float(similarities[i].max()) for i in indices], default=0)) * 100, 2),
                pipeline_version="v2", requirement_assessments=assessments,
                essential_supported=sum(a.status == "supported" for a in required), essential_total=len(required),
                essential_unknown=sum(a.status == "unknown" for a in required),
                essential_contradicted=sum(a.status == "contradicted" for a in required),
                checks=[f"{a.title}: {a.status}. {a.reasoning}" for a in assessments]))
        priorities = {str(c.candidate_id): language_priority(c, job) for c in candidates}
        for row in rows:
            row.language_priority = priorities[str(row.candidate_id)]
        rows.sort(key=lambda row: (row.language_priority, -row.pre_screen_score, str(row.candidate_id)))
        for rank, row in enumerate(rows, 1):
            row.rank = row.initial_rank = rank
        self.diagnostics["timings_ms"]["hybrid_total"] = round((time.perf_counter() - started) * 1000, 2)
        return rows

    @staticmethod
    def assess(candidate, requirement, passages, similarity, passage_scores=None):
        terms = requirement_terms(requirement.title, requirement.description)
        text = " ".join(unit.text for unit in passages)
        found = [term for term in terms if term_matches(text, term)]
        fraction = len(found) / len(terms) if terms else 0
        demonstrated = any(unit.strength == "demonstrated" and any(term_matches(unit.text, term) for term in terms) for unit in passages)
        score = fraction * (100 if demonstrated else 55)
        status = "supported" if fraction == 1 and demonstrated else "partial" if found else "unknown"
        reasoning = f"{len(found)}/{len(terms)} terms supported in {'documented work or qualifications' if demonstrated else 'listed or incomplete evidence'}."
        years = None
        req_text = f"{requirement.title} {requirement.description}"
        # Generic semantic relevance is a retrieval signal, never credential proof.
        if not found and similarity >= .55:
            status, score = "partial", 20
            reasoning = "Related passage retrieved; required competence remains unverified."
        if not found:
            transfer = SkillEquivalenceService.find_transferable_skill(candidate.anonymized_skills, candidate.anonymized_work_experiences, requirement.title, requirement.description)
            if transfer:
                status, score = "partial", 35
                reasoning = f"Transferable {transfer[0]} experience; {transfer[1]} is not directly verified."
        if re.search(r"\b(degree|bachelor|master|phd|diploma|bsc|msc|university)\b", req_text, re.I):
            check = SkillEquivalenceService.evaluate_degree_hierarchy(candidate.anonymized_education, requirement.title, requirement.description)
            status, score = ("supported", 100) if check and check[0] else ("unknown", 0)
            reasoning = "Matching documented qualification." if check and check[0] else "Required qualification is not verified; other qualifications do not prove its absence."
        language = language_assessment(candidate, requirement)
        if language:
            status, score, reasoning = language
        minimum = requirement.minimum_years_experience
        if minimum is None:
            match = re.search(r"(\d+)\s*\+?\s*years?", req_text, re.I)
            minimum = int(match.group(1)) if match else None
        if minimum and minimum > 0:
            years, dated = relevant_years(candidate, terms, req_text)
            duration_score = 100 * min(years / minimum, 1)
            score = min(score, duration_score) if terms else duration_score
            if not terms:
                status = "supported" if years >= minimum and dated else "partial" if years > 0 else "unknown"
                reasoning = "Professional experience assessed from documented roles."
            if years < minimum or not dated:
                status = "partial" if years > 0 else "unknown"
            reasoning += f" {years:.1f}/{minimum} relevant years documented; {'dated intervals merged' if dated else 'missing dates need clarification'}."
        if requirement.category == "soft_skill":
            status, score, reasoning = "unknown", 0, "Interpretive criterion reserved for deep evaluation and recruiter review."
        if any(re.search(r"\b(?:no|without|not)\s+(?:\w+\s+){0,3}" + re.escape(term) + r"\b", text, re.I) for term in found):
            status, score, reasoning = "unknown", 0, "Negative or conflicting evidence found; recruiter clarification is required."
        # Return only passages relevant to this check, never unrelated quotes as proof.
        evidence = [unit for unit in passages if any(term_matches(unit.text, term) for term in terms) or (passage_scores or {}).get(unit.id, 0) >= .55]
        if minimum and minimum > 0 and not terms:
            evidence = [unit for unit in passages if unit.section.startswith("experience[")]
        if language:
            evidence = [unit for unit in evidence if unit.section.startswith("languages[")]
        return RequirementAssessment(requirement_id=requirement.id, title=requirement.title,
            category=requirement.category, weight=requirement.weight, status=status, score=round(score, 2),
            reasoning=reasoning, evidence=evidence, documented_years=years)

    def rerank(self, rows, job, reranker, pool_size):
        pool = rows[:pool_size]
        pairs, references = [], []
        descriptions = {r.id: f"{r.title}: {r.description}" for r in job.requirements}
        for row in pool:
            for assessment in row.requirement_assessments:
                if assessment.category == "soft_skill":
                    continue
                for evidence in assessment.evidence:
                    if len(pairs) >= 6000:
                        raise ValueError("Reranking pair budget exceeded; reduce pool size.")
                    pairs.append((descriptions[assessment.requirement_id], evidence.text))
                    references.append((row, assessment))
        if not pairs:
            self.diagnostics["warnings"].append("No supported evidence pairs available for reranking.")
            return rows
        scores = np.asarray(reranker.predict(pairs), dtype=float).reshape(-1)
        if len(scores) != len(pairs) or not np.isfinite(scores).all():
            raise ValueError("Reranker returned invalid scores")
        for (row, assessment), score in zip(references, scores):
            assessment.rerank_score = max(assessment.rerank_score if assessment.rerank_score is not None else -math.inf, float(score))
        for row in pool:
            scored = [a for a in row.requirement_assessments if a.rerank_score is not None]
            if scored:
                row.rerank_score = sum(a.weight * a.rerank_score for a in scored) / sum(a.weight for a in scored)
                row.reranked = True
        # Joint relevance refines evidence ranking, but cannot erase explicit contradictions
        # or substitute a relevance logit for the separate 0-100 pre-screen score.
        pool.sort(key=lambda row: (row.language_priority, row.essential_contradicted, -(row.pre_screen_score // 10),
            -(row.rerank_score if row.rerank_score is not None else -math.inf), row.initial_rank))
        result = [*pool, *rows[pool_size:]]
        for rank, row in enumerate(result, 1):
            row.rank = rank
        return result

"""
backend/services/vector_store.py
ChromaDB vector store manager for local embeddings and asymmetric semantic retrieval.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from backend.schemas.cv import AnonymizedCandidate
from backend.schemas.job import JobDescription, JobRequirement


DEFAULT_CHROMA_PATH = "./data/chroma_db"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class VectorStoreService:
    """Service managing local ChromaDB collections for candidate chunks and job criteria."""

    def __init__(
        self,
        persist_directory: str = DEFAULT_CHROMA_PATH,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.persist_directory = persist_directory
        self.model_name = model_name
        self.client = chromadb.PersistentClient(path=persist_directory)
        self._embedding_fn = None
        self._candidate_collection = None
        self._job_collection = None

    @property
    def embedding_fn(self):
        if self._embedding_fn is None:
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.model_name
            )
        return self._embedding_fn

    @property
    def candidate_collection(self):
        if self._candidate_collection is None:
            self._candidate_collection = self.client.get_or_create_collection(
                name="candidate_chunks",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
        return self._candidate_collection

    @candidate_collection.setter
    def candidate_collection(self, value):
        self._candidate_collection = value

    @property
    def job_collection(self):
        if self._job_collection is None:
            self._job_collection = self.client.get_or_create_collection(
                name="job_requirements",
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
        return self._job_collection

    @job_collection.setter
    def job_collection(self, value):
        self._job_collection = value



    def index_candidate(self, candidate: AnonymizedCandidate) -> int:
        """
        Chunks candidate experience bullet points and skills, then indexes them in ChromaDB.

        Returns:
            Number of indexed chunks.
        """
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        ids: List[str] = []

        # 1. Iterate through each work experience and chunk individual accomplishment bullets
        for exp_idx, experience in enumerate(candidate.anonymized_work_experiences):
            for b_idx, bullet in enumerate(experience.work_description):
                if not bullet or not bullet.strip():
                    continue

                # Attach provenance metadata so the matching agent knows the source role and company
                metadata = {
                    "candidate_id": str(candidate.candidate_id),
                    "type": "work_experience",
                    "job_title": experience.job_title,
                    "company_name": experience.company_name,
                    "experience_index": exp_idx,
                    "bullet_index": b_idx,
                }
                # Guarantee a globally unique chunk ID using candidate UUID + experience index + bullet index
                chunk_id = f"candidate_{candidate.candidate_id}_exp_{exp_idx}_b_{b_idx}"

                documents.append(bullet.strip())
                metadatas.append(metadata)
                ids.append(chunk_id)

        # 2. Add an aggregated skills chunk if the candidate has listed skills
        if candidate.anonymized_skills:
            skills_text = ", ".join(candidate.anonymized_skills)
            documents.append(f"Skills: {skills_text}")
            metadatas.append({
                "candidate_id": str(candidate.candidate_id),
                "type": "skills",
                "experience_index": -1,
                "bullet_index": -1,
            })
            ids.append(f"candidate_{candidate.candidate_id}_skills")

        # 3. Add project chunks
        for p_idx, project in enumerate(getattr(candidate, "anonymized_projects", [])):
            proj_desc = " ".join(project.description)
            tech_str = f" Technologies: {', '.join(project.technologies)}." if project.technologies else ""
            proj_content = f"Project: {project.project_name}.{tech_str} {proj_desc}".strip()
            documents.append(proj_content)
            metadatas.append({
                "candidate_id": str(candidate.candidate_id),
                "type": "project",
                "job_title": f"Project: {project.project_name}",
                "company_name": "Independent/Academic",
                "experience_index": p_idx,
                "bullet_index": 0,
            })
            ids.append(f"candidate_{candidate.candidate_id}_proj_{p_idx}")

        # 4. Add languages chunk
        langs = getattr(candidate, "anonymized_languages", [])
        if langs:
            lang_strings = [
                f"{lang.language} ({lang.proficiency})" if lang.proficiency else lang.language
                for lang in langs
            ]
            documents.append(f"Languages: {', '.join(lang_strings)}")
            metadatas.append({
                "candidate_id": str(candidate.candidate_id),
                "type": "languages",
                "job_title": "Languages",
                "company_name": "Candidate Profile",
                "experience_index": -1,
                "bullet_index": -1,
            })
            ids.append(f"candidate_{candidate.candidate_id}_languages")

        # 5. Add custom fallback sections chunks
        for s_idx, sec in enumerate(getattr(candidate, "anonymized_custom_sections", [])):
            if not sec.is_relevant or not sec.items:
                continue
            sec_content = f"{sec.section_title}: " + "; ".join(sec.items)
            documents.append(sec_content)
            metadatas.append({
                "candidate_id": str(candidate.candidate_id),
                "type": "custom_section",
                "job_title": sec.section_title,
                "company_name": "Additional Qualifications",
                "experience_index": s_idx,
                "bullet_index": 0,
            })
            ids.append(f"candidate_{candidate.candidate_id}_sec_{s_idx}")

        # 6. Add education chunks
        for edu_idx, edu in enumerate(getattr(candidate, "anonymized_education", [])):
            edu_content = f"Degree: {edu.degree_title} in {edu.field_of_study or 'General'} from {edu.institution_name}"
            if edu.graduation_year:
                edu_content += f" ({edu.graduation_year})"
            documents.append(edu_content)
            metadatas.append({
                "candidate_id": str(candidate.candidate_id),
                "type": "education",
                "job_title": edu.degree_title,
                "company_name": edu.institution_name,
                "experience_index": edu_idx,
                "bullet_index": 0,
            })
            ids.append(f"candidate_{candidate.candidate_id}_edu_{edu_idx}")

        # 7. Idempotently upsert all chunks into ChromaDB (safe against re-indexing existing IDs)
        if documents:
            self.candidate_collection.upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

        # 4. Return total count of chunks added
        return len(documents)

    def query_candidate_chunks(
        self,
        candidate_id: UUID,
        query_text: str,
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic search across a specific candidate's indexed chunks.

        Returns:
            List of matching chunks with document text, score/distance, and metadata.
        """
        # 1. Guard against querying an empty collection
        total_available = self.candidate_collection.count()
        if total_available == 0:
            return []

        # 2. Cap n_results to the available count to prevent ChromaDB boundary errors
        limit = min(n_results, total_available)

        # 3. Query ChromaDB filtered strictly by candidate_id to prevent cross-candidate data leakage
        results = self.candidate_collection.query(
            query_texts=[query_text],
            where={"candidate_id": str(candidate_id)},
            n_results=limit,
        )

        # 4. Unpack ChromaDB's 2D batch response structure into a clean list of dictionaries
        formatted: List[Dict[str, Any]] = []
        if results and results.get("documents") and results["documents"]:
            doc_list = results["documents"][0]
            dist_list = results.get("distances", [[]])[0]
            meta_list = results.get("metadatas", [[]])[0]

            for i, doc in enumerate(doc_list):
                formatted.append({
                    "text": doc,
                    "distance": dist_list[i] if i < len(dist_list) else 0.0,
                    "metadata": meta_list[i] if i < len(meta_list) else {},
                })

        return formatted

    def reset(self) -> None:
        """Helper to clear collections for testing and test isolation."""
        try:
            self.client.delete_collection("candidate_chunks")
            self.client.delete_collection("job_requirements")
        except Exception:
            pass

        # Re-initialize empty collections with cosine distance metric
        self.candidate_collection = self.client.get_or_create_collection(
            name="candidate_chunks",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self.job_collection = self.client.get_or_create_collection(
            name="job_requirements",
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

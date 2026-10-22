"""
backend/services/tenure_calculator.py
Unified tenure and experience calculator with interval union, overlap merging,
explicit skill scope, and unknown duration handling (E6).
"""

from datetime import date, datetime
import re
from typing import List, Optional, Set, Tuple

from dateutil.parser import parse

from backend.schemas.cv import AnonymizedCandidate, WorkExperience


def month_index(value: Optional[str], end: bool = False) -> Optional[int]:
    """Parse a date string into an integer month index (year * 12 + month - 1)."""
    if not value or not str(value).strip():
        return None
    val_clean = str(value).strip().lower()
    if val_clean in {"present", "current", "now", "ongoing"}:
        today = date.today()
        return today.year * 12 + today.month - 1
    try:
        parsed = parse(val_clean, default=datetime(2000, 12 if end else 1, 1))
        return parsed.year * 12 + parsed.month - 1
    except (ValueError, TypeError, OverflowError):
        return None


TECH_ALIASES = {
    "postgres": ["postgresql"],
    "postgresql": ["postgres"],
    "js": ["javascript"],
    "javascript": ["js"],
    "ts": ["typescript"],
    "typescript": ["ts"],
    "k8s": ["kubernetes"],
    "kubernetes": ["k8s"],
    "node.js": ["nodejs", "node"],
    "nodejs": ["node.js", "node"],
    "csharp": ["c#"],
    "c#": ["csharp"],
    "golang": ["go"],
    "react.js": ["react"],
    "reactjs": ["react"],
    "vue.js": ["vue"],
    "vuejs": ["vue"],
    "aws": ["amazon web services"],
    "gcp": ["google cloud platform", "google cloud"],
}


def role_matches_term(role: WorkExperience, term: str) -> bool:
    """Check if a single work experience entry matches a target term or skill."""
    target = term.lower().strip()
    if not target:
        return False

    targets = {target}
    for alias in TECH_ALIASES.get(target, []):
        targets.add(alias)

    for t in targets:
        pat = re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)

        # 1. Skills list
        for s in role.skills_used:
            if t == s.lower() or pat.search(s):
                return True

        # 2. Job title
        if role.job_title and pat.search(role.job_title):
            return True

        # 3. Work description
        for desc in role.work_description:
            if desc and pat.search(desc):
                return True

    return False


class TenureCalculator:
    """Calculates deduplicated, verified calendar tenure without inventing missing dates."""

    @classmethod
    def calculate_skill_tenure(
        cls,
        experiences: List[WorkExperience],
        term: Optional[str] = None,
    ) -> Tuple[float, bool]:
        """
        Calculate calendar years for a specific skill (or all roles if term is None).
        Returns (years, is_fully_dated). Overlapping roles are merged via set union.
        Missing dates are never assumed to be 12 months.
        """
        if not experiences:
            return 0.0, True

        dated_months: Set[int] = set()
        stated_undated_months: List[int] = []
        has_undated = False

        for role in experiences:
            if term is not None and not role_matches_term(role, term):
                continue

            start = month_index(role.start_date, end=False)
            end = month_index(role.end_date, end=True)

            if start is not None and end is not None and end >= start:
                dated_months.update(range(start, end + 1))
            else:
                has_undated = True
                if role.duration_months and role.duration_months > 0:
                    stated_undated_months.append(role.duration_months)

        # To prevent double-counting undated roles on top of dated periods without proof of non-overlap:
        total_months = max(len(dated_months), sum(stated_undated_months))
        return round(total_months / 12.0, 1), not has_undated

    @classmethod
    def calculate_tenure_for_skill(
        cls,
        experiences: List[WorkExperience],
        skill_or_tool: str,
    ) -> float:
        """Compatibility wrapper for deep matching agent: returns calendar years."""
        years, _ = cls.calculate_skill_tenure(experiences, skill_or_tool)
        return years

    @classmethod
    def calculate_requirement_tenure(
        cls,
        candidate: AnonymizedCandidate,
        terms: List[str],
        requirement_text: str = "",
    ) -> Tuple[float, bool]:
        """
        Calculates tenure for a requirement across candidate work history.
        - Disjunctive requirements ("or", "either"): max tenure across terms.
        - Conjunctive requirements ("and" or compound terms): min tenure across terms,
          ensuring a role with only 1 skill does not falsely credit the compound requirement.
        - Overall experience (no terms): union across all roles.
        """
        experiences = candidate.anonymized_work_experiences or []
        if not experiences:
            return 0.0, True

        if not terms:
            return cls.calculate_skill_tenure(experiences, term=None)

        if len(terms) == 1:
            return cls.calculate_skill_tenure(experiences, term=terms[0])

        # Multi-term handling: check disjunction vs conjunction
        req_lower = requirement_text.lower()
        is_disjunctive = bool(re.search(r"\b(or|either)\b", req_lower))

        per_term_results = [cls.calculate_skill_tenure(experiences, term=t) for t in terms]

        if is_disjunctive:
            # At least one skill must be satisfied; take highest verified tenure
            best_years = max(r[0] for r in per_term_results)
            all_dated = all(r[1] for r in per_term_results)
            return best_years, all_dated
        else:
            # Conjunctive: candidate must satisfy tenure across all required skills
            # A role having only Java will produce 0 Python years, preventing over-crediting
            min_years = min(r[0] for r in per_term_results)
            all_dated = all(r[1] for r in per_term_results)
            return min_years, all_dated

    @classmethod
    def calculate_experience_years(
        cls,
        candidate: AnonymizedCandidate,
        terms: List[str],
        requirement_text: str = "",
    ) -> float:
        """Compatibility wrapper returning float years."""
        years, _ = cls.calculate_requirement_tenure(candidate, terms, requirement_text)
        return years

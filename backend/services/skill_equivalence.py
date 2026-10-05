"""
backend/services/skill_equivalence.py
Deterministic Skill Equivalence, Transferable Competencies, and Hierarchical Evaluation Service.
Prevents false rejections due to strict verbatim phrasing, adjacent technologies,
higher qualification levels, or unstated explicit years.
"""

from typing import Dict, List, Optional, Set, Tuple
import re

from backend.schemas.cv import AnonymizedCandidate, Education, LanguageSkill, WorkExperience
from backend.schemas.job import JobRequirement


# =============================================================================
# 1. Tech & Tool Equivalence Clusters
# =============================================================================
EQUIVALENCE_CLUSTERS: List[Dict[str, List[str]]] = [
    {
        "category": "Cloud Infrastructure",
        "family": "cloud_provider",
        "members": [
            "aws", "amazon web services", "ec2", "s3", "iam", "lambda", "ecs", "eks",
            "gcp", "google cloud", "google cloud platform", "gke", "bigquery", "cloud run",
            "azure", "microsoft azure", "azure devops", "aks", "blob storage",
            "openstack", "digitalocean", "ovhcloud"
        ],
    },
    {
        "category": "Relational Databases",
        "family": "rdbms",
        "members": [
            "postgresql", "postgres", "mysql", "mariadb", "oracle db", "oracle database",
            "ms sql", "sql server", "microsoft sql", "sqlite", "relational database", "rdbms"
        ],
    },
    {
        "category": "Document & NoSQL Stores",
        "family": "nosql",
        "members": [
            "mongodb", "couchbase", "dynamodb", "documentdb", "cassandra", "scylladb", "couchdb"
        ],
    },
    {
        "category": "Cache & Message Queues",
        "family": "messaging_cache",
        "members": [
            "kafka", "apache kafka", "rabbitmq", "pulsar", "aws sqs", "redis", "celery", "activemq"
        ],
    },
    {
        "category": "Containerization & Orchestration",
        "family": "containers",
        "members": [
            "kubernetes", "k8s", "docker swarm", "openshift", "nomad", "podman", "docker", "containerd", "ecs"
        ],
    },
    {
        "category": "Frontend Frameworks",
        "family": "frontend_frameworks",
        "members": [
            "react", "react.js", "next.js", "nextjs", "vue", "vue.js", "nuxt", "angular", "svelte", "sveltekit"
        ],
    },
    {
        "category": "Python Web Frameworks",
        "family": "python_web",
        "members": [
            "fastapi", "flask", "django", "tornado", "aiohttp", "starlette", "sanic"
        ],
    },
    {
        "category": "Node / JS Web Frameworks",
        "family": "node_web",
        "members": [
            "express", "express.js", "nestjs", "koa", "fastify", "hapi"
        ],
    },
    {
        "category": "Infrastructure as Code",
        "family": "iac",
        "members": [
            "terraform", "terragrunt", "opentofu", "pulumi", "aws cdk", "cloudformation", "bicep", "ansible"
        ],
    },
    {
        "category": "CI/CD & Automation",
        "family": "cicd",
        "members": [
            "github actions", "gitlab ci", "jenkins", "circleci", "travis ci", "argo cd", "argocd", "flux", "tekton"
        ],
    },
    {
        "category": "Observability & Metrics",
        "family": "observability",
        "members": [
            "prometheus", "grafana", "datadog", "new relic", "dynatrace", "elk stack", "opentelemetry", "splunk"
        ],
    },
    {
        "category": "Distributed Data Processing",
        "family": "big_data",
        "members": [
            "spark", "apache spark", "pyspark", "flink", "dbt", "hadoop", "hive", "airflow", "prefect", "dagster"
        ],
    },
]


# =============================================================================
# 2. Hierarchical Scales (Languages & Academic Degrees)
# =============================================================================
CEFR_LEVELS = {
    "native": 6,
    "mothertongue": 6,
    "mother tongue": 6,
    "bilingual": 6,
    "c2": 6,
    "verhandlungssicher": 6,
    "c1": 5,
    "fluent": 5,
    "fließend": 5,
    "advanced": 5,
    "full professional": 5,
    "b2": 4,
    "upper intermediate": 4,
    "professional working": 4,
    "gut": 4,
    "konversationssicher": 4,
    "b1": 3,
    "intermediate": 3,
    "working proficiency": 3,
    "a2": 2,
    "elementary": 2,
    "pre-intermediate": 2,
    "grundkenntnisse": 2,
    "a1": 1,
    "beginner": 1,
    "basic": 1,
}

DEGREE_LEVELS = {
    "phd": 4,
    "doctorate": 4,
    "dr.": 4,
    "dphil": 4,
    "master": 3,
    "msc": 3,
    "m.sc": 3,
    "ma": 3,
    "m.a": 3,
    "meng": 3,
    "mba": 3,
    "magister": 3,
    "bachelor": 2,
    "bsc": 2,
    "b.sc": 2,
    "ba": 2,
    "b.a": 2,
    "beng": 2,
    "licenta": 2,
    "undergraduate": 2,
    "associate": 1,
    "diploma": 1,
    "high school": 1,
}

TECH_NAME_MAP = {
    "aws": "AWS",
    "amazon web services": "AWS",
    "ec2": "AWS EC2",
    "s3": "AWS S3",
    "iam": "AWS IAM",
    "lambda": "AWS Lambda",
    "ecs": "AWS ECS",
    "eks": "AWS EKS",
    "gcp": "GCP",
    "google cloud": "Google Cloud",
    "google cloud platform": "Google Cloud",
    "gke": "GKE",
    "bigquery": "BigQuery",
    "cloud run": "Cloud Run",
    "azure": "Azure",
    "microsoft azure": "Microsoft Azure",
    "azure devops": "Azure DevOps",
    "aks": "AKS",
    "blob storage": "Azure Blob Storage",
    "openstack": "OpenStack",
    "digitalocean": "DigitalOcean",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "oracle db": "Oracle DB",
    "oracle database": "Oracle DB",
    "ms sql": "MS SQL",
    "sql server": "SQL Server",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "couchbase": "Couchbase",
    "dynamodb": "DynamoDB",
    "documentdb": "DocumentDB",
    "cassandra": "Cassandra",
    "scylladb": "ScyllaDB",
    "kafka": "Apache Kafka",
    "apache kafka": "Apache Kafka",
    "rabbitmq": "RabbitMQ",
    "pulsar": "Apache Pulsar",
    "aws sqs": "AWS SQS",
    "redis": "Redis",
    "celery": "Celery",
    "activemq": "ActiveMQ",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "docker": "Docker",
    "podman": "Podman",
    "openshift": "OpenShift",
    "nomad": "Nomad",
    "react": "React",
    "react.js": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "vue": "Vue",
    "vue.js": "Vue",
    "nuxt": "Nuxt",
    "angular": "Angular",
    "svelte": "Svelte",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "express": "Express.js",
    "express.js": "Express.js",
    "nestjs": "NestJS",
    "terraform": "Terraform",
    "terragrunt": "Terragrunt",
    "ansible": "Ansible",
    "pulumi": "Pulumi",
    "cloudformation": "CloudFormation",
    "github actions": "GitHub Actions",
    "gitlab ci": "GitLab CI",
    "jenkins": "Jenkins",
    "argo cd": "ArgoCD",
    "argocd": "ArgoCD",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "datadog": "Datadog",
    "opentelemetry": "OpenTelemetry",
    "spark": "Apache Spark",
    "apache spark": "Apache Spark",
    "pyspark": "PySpark",
    "flink": "Apache Flink",
    "dbt": "dbt",
    "airflow": "Apache Airflow",
}


def format_tech_name(term: str) -> str:
    """Formats technical terms with proper capitalization."""
    term_lower = term.strip().lower()
    return TECH_NAME_MAP.get(term_lower, term.title())


class SkillEquivalenceService:
    """Service providing fuzzy, transferable, and hierarchical competence evaluation."""

    @staticmethod
    def find_transferable_skill(
        candidate_skills: List[str],
        candidate_experiences: List[WorkExperience],
        requirement_title: str,
        requirement_description: str,
    ) -> Optional[Tuple[str, str, str]]:
        """
        Detects if a candidate possesses a transferable/equivalent technology
        matching an unmet requirement.

        Returns:
            Tuple of (detected_candidate_skill, target_requirement_skill, family_category)
            or None if no equivalent detected.
        """
        req_text = f"{requirement_title} {requirement_description}".lower()

        # Collect candidate tokens
        cand_tokens: Set[str] = {s.lower().strip() for s in candidate_skills}
        for exp in candidate_experiences:
            for s in exp.skills_used:
                cand_tokens.add(s.lower().strip())
            for line in exp.work_description:
                for word in re.findall(r"\b[a-zA-Z0-9_\-\.+#]+\b", line.lower()):
                    cand_tokens.add(word)

        for cluster in EQUIVALENCE_CLUSTERS:
            members = cluster["members"]
            # Check if requirement specifically calls for any member in this cluster
            target_matches = [m for m in members if re.search(r"\b" + re.escape(m) + r"\b", req_text)]
            if not target_matches:
                continue

            target_term = target_matches[0]

            # If candidate already possesses the target technology directly, it's not a transferable fallback
            has_target = any(
                re.search(r"\b" + re.escape(t) + r"\b", cand_tok)
                for t in target_matches
                for cand_tok in cand_tokens
            )
            if has_target:
                continue

            # Check if candidate possesses ANY OTHER member of the same cluster
            for cand_skill in cand_tokens:
                for member in members:
                    if member == target_term or member in target_matches:
                        continue
                    # Match on word boundary to prevent false substring matches (e.g. 'iam' in 'parliament')
                    if re.search(r"\b" + re.escape(member) + r"\b", cand_skill):
                        return (format_tech_name(member), format_tech_name(target_term), cluster["category"])

        return None

    @staticmethod
    def evaluate_language_hierarchy(
        languages: List[LanguageSkill],
        requirement_title: str,
        requirement_description: str,
    ) -> Optional[Tuple[bool, str, str]]:
        """
        Determines whether a candidate's language proficiencies satisfy or exceed
        the target requirement via CEFR hierarchy (e.g., C1 satisfies B2).

        Returns:
            Tuple of (is_satisfied, candidate_language_level, required_language_level)
            or None if requirement is not language-specific.
        """
        req_text = f"{requirement_title} {requirement_description}".lower()

        target_lang = None
        for lang in ["german", "english", "french", "spanish", "italian", "romanian", "dutch"]:
            if lang in req_text:
                target_lang = lang
                break

        if not target_lang:
            return None

        # Determine target CEFR level from requirement text
        target_score = 3  # default B1 if unspecified
        target_level_str = "B1"
        for term, level in CEFR_LEVELS.items():
            if re.search(r"\b" + re.escape(term) + r"\b", req_text):
                if level > target_score:
                    target_score = level
                    target_level_str = term.upper()

        # Find matching candidate language
        for cand_lang in languages:
            c_name = cand_lang.language.lower()
            if target_lang in c_name:
                cand_prof = (cand_lang.proficiency or "").lower()
                cand_score = None
                for term, level in CEFR_LEVELS.items():
                    if re.search(r"\b" + re.escape(term) + r"\b", cand_prof) or re.search(r"\b" + re.escape(term) + r"\b", c_name):
                        if cand_score is None or level > cand_score:
                            cand_score = level

                if cand_score is None:
                    cand_score = 4  # default assumption if listed without level (B2 working)

                if cand_score >= target_score:
                    return (True, cand_lang.proficiency or "Fluent", target_level_str)
                else:
                    return (False, cand_lang.proficiency or "Basic", target_level_str)

        return None

    @staticmethod
    def evaluate_degree_hierarchy(
        education_list: List[Education],
        requirement_title: str,
        requirement_description: str,
    ) -> Optional[Tuple[bool, str, str]]:
        """
        Determines whether candidate's degree satisfies or exceeds required academic level
        (e.g., MSc/PhD strictly satisfies Bachelor's requirement).

        Returns:
            Tuple of (is_satisfied, candidate_degree, required_degree)
            or None if requirement is not academic degree-related.
        """
        req_text = f"{requirement_title} {requirement_description}".lower()

        # Check if this requirement is asking for a degree
        is_degree_req = any(kw in req_text for kw in [
            "bachelor", "master", "phd", "degree", "diploma", "bsc", "msc", "licenta"
        ])
        if not is_degree_req:
            return None

        # Target degree required level
        target_level = 2  # default Bachelor level
        target_degree_str = "Bachelor's Degree"
        for term, level in DEGREE_LEVELS.items():
            if re.search(r"\b" + re.escape(term) + r"\b", req_text):
                target_level = max(target_level, level)
                target_degree_str = term.upper()

        if not education_list:
            return None

        # Check highest degree achieved by candidate
        highest_cand_level = 0
        best_cand_degree = "No Degree"
        for edu in education_list:
            d_title = edu.degree_title.lower()
            for term, level in DEGREE_LEVELS.items():
                if term in d_title:
                    if level > highest_cand_level:
                        highest_cand_level = level
                        best_cand_degree = edu.degree_title

        if highest_cand_level >= target_level:
            return (True, best_cand_degree, target_degree_str)
        elif highest_cand_level > 0:
            return (False, best_cand_degree, target_degree_str)

        return None

    @staticmethod
    def calculate_tenure_for_skill(
        experiences: List[WorkExperience],
        skill_or_tool: str,
    ) -> float:
        """
        Aggregates estimated calendar years across all work experience entries
        where the skill or tool is listed.
        """
        target = skill_or_tool.lower().strip()
        total_months = 0

        for exp in experiences:
            # Check if skill is in skills_used or description
            skills_lower = [s.lower() for s in exp.skills_used]
            desc_lower = " ".join(exp.work_description).lower()

            if any(target in s for s in skills_lower) or target in desc_lower or target in exp.job_title.lower():
                duration = exp.duration_months or 12  # default 1 year per role if unstated
                total_months += duration

        return round(total_months / 12.0, 1)

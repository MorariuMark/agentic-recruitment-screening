"""
scripts/generate_and_seed_cohort.py
Deterministic, highly-varied enterprise synthetic cohort generator.
Generates realistic candidate CVs calibrated against the 6 enterprise Job Descriptions:
- 35% Strong Matches (high experience, matching stack & keywords)
- 30% Borderline Matches (adjacent experience, minor gaps -> triggers HITL)
- 35% Clear Rejects / Underqualified (major missing requirements)

Persists records into SQLite (recruitment.db) and embeds chunks into ChromaDB (data/chroma_db).
"""

import asyncio
import os
import random
import uuid
from datetime import datetime
from typing import List, Tuple

from backend.db.repository import DatabaseRepository
from backend.schemas.cv import (
    ContactInfo,
    Education,
    LanguageSkill,
    ParsedCV,
    Project,
    WorkExperience,
)
from backend.services.pii_scrubber import PIIScrubber
from backend.services.vector_store import VectorStoreService

# Seed for reproducible realism
random.seed(42)

FIRST_NAMES = [
    "Alexandru", "Andrei", "Mihai", "Cristian", "Gabriel", "Stefan", "Radu", "Bogdan",
    "Elena", "Ioana", "Maria", "Andreea", "Diana", "Roxana", "Laura", "Raluca",
    "Florin", "Adrian", "Vlad", "Cosmin", "Daniel", "Dan", "Sorin", "Teodor",
    "Ana", "Carmen", "Simona", "Alina", "Madalina", "Oana", "Bianca", "Patricia",
    "Marcus", "Lukas", "Sophie", "Clara", "Thomas", "Jan", "Mateusz", "Viktor"
]

LAST_NAMES = [
    "Popescu", "Ionescu", "Radu", "Dumitrescu", "Stoica", "Gheorghe", "Stan", "Matei",
    "Ciobanu", "Rusu", "Munteanu", "Constantin", "Dobre", "Toma", "Marin", "Iliescu",
    "Serban", "Moldovan", "Nistor", "Enache", "Stanciu", "Dragomir", "Petrescu",
    "Schmidt", "Müller", "Novak", "Kowalski", "Dumont", "Weber", "Fischer"
]

CITIES = ["Bucharest, Romania", "Cluj-Napoca, Romania", "Timisoara, Romania", "Iasi, Romania", "Brasov, Romania", "Sibiu, Romania"]

COMPANIES = [
    "Endava", "Bitdefender", "UiPath", "Atos Romania", "Continental", "Adobe Romania",
    "Amazon Development Center", "Microsoft Romania", "ING Hubs Romania", "Deutsche Bank Tech",
    "Vodafone Shared Services", "Orange Services", "FintechOS", "Zitec", "Tremend Software",
    "Luxoft Romania", "Accenture Tech Labs", "Playtika", "Cognizant Softvision", "EPAM Systems",
    "N-able", "Thales Systems", "Cegeka", "EveryMatrix", "CrowdStrike Romania"
]

UNIVERSITIES = [
    ("Politehnica University of Bucharest", "Computer Science & Automatic Control"),
    ("Politehnica University of Bucharest", "Electronics, Telecommunications & IT"),
    ("Babes-Bolyai University of Cluj-Napoca", "Mathematics and Computer Science"),
    ("Technical University of Cluj-Napoca", "Automation and Computer Science"),
    ("Politehnica University of Timisoara", "Computer Engineering"),
    ("Alexandru Ioan Cuza University of Iasi", "Computer Science"),
    ("University of Bucharest", "Faculty of Mathematics and Informatics")
]

DEGREES = ["Bachelor of Science in Computer Science", "Master of Science in Software Engineering", "Bachelor of Engineering in IT Systems", "Master of Science in Distributed Systems & AI"]

ROLES_PROFILES = [
    "cloud_devops",
    "fullstack",
    "ml_genai",
    "data_eng",
    "security_appsec",
    "eng_manager"
]

PROFILE_SKILLS = {
    "cloud_devops": {
        "strong": ["Kubernetes", "Docker", "Terraform", "AWS", "EKS", "GCP", "CI/CD", "GitHub Actions", "ArgoCD", "Helm", "Prometheus", "Grafana", "Python", "Bash", "Linux", "OpenTofu"],
        "borderline": ["Docker", "AWS", "Jenkins", "Ansible", "Linux", "Git", "Bash", "Terraform", "Python", "CloudFormation"],
        "reject": ["HTML", "CSS", "WordPress", "PHP", "Manual Testing", "Jira", "Photoshop", "SEO"]
    },
    "fullstack": {
        "strong": ["React 19", "React", "Next.js", "TypeScript", "Node.js", "FastAPI", "Python", "PostgreSQL", "TailwindCSS", "REST APIs", "GraphQL", "Docker", "Jest", "State Management", "Git"],
        "borderline": ["React", "JavaScript", "HTML5", "CSS3", "Node.js", "Express", "MongoDB", "REST API", "Git", "Redux"],
        "reject": ["AutoCAD", "Excel", "Data Entry", "Salesforce CRM", "Manual QA", "Copywriting"]
    },
    "ml_genai": {
        "strong": ["Python", "PyTorch", "LLMs", "RAG Systems", "LangChain", "LlamaIndex", "ChromaDB", "Vector Databases", "vLLM", "Transformers", "HuggingFace", "FastAPI", "Docker", "MLOps", "Ollama"],
        "borderline": ["Python", "scikit-learn", "Pandas", "NumPy", "SQL", "Tableau", "TensorFlow", "Statistics", "Machine Learning", "Jupyter"],
        "reject": ["IT Support", "Hardware Repair", "Network Cabling", "Windows Server", "Helpdesk", "Ticketing"]
    },
    "data_eng": {
        "strong": ["Apache Spark", "Python", "SQL", "Apache Kafka", "Snowflake", "dbt", "Airflow", "Databricks", "Data Modeling", "ETL Pipelines", "Docker", "AWS S3", "Delta Lake"],
        "borderline": ["SQL", "PostgreSQL", "Python", "SSIS", "PowerBI", "Tableau", "Excel", "Data Warehousing", "ETL"],
        "reject": ["Social Media Marketing", "Content Creation", "Graphic Design", "Photoshop", "Illustrator"]
    },
    "security_appsec": {
        "strong": ["Application Security", "Cloud Security", "AWS Security", "Kubernetes Security", "Threat Modeling", "SAST", "DAST", "SOC 2", "ISO 27001", "EU AI Act", "Penetration Testing", "OWASP Top 10", "Python", "Trivy"],
        "borderline": ["Network Security", "Firewalls", "VPN", "Linux Administration", "Wireshark", "Vulnerability Scanning", "Active Directory", "SIEM", "Splunk"],
        "reject": ["Customer Support", "Telemarketing", "Office Administration", "Reception", "Billing"]
    },
    "eng_manager": {
        "strong": ["Engineering Management", "Technical Leadership", "Agile & Scrum", "System Architecture", "AI Platform Delivery", "People Management", "Strategic Roadmapping", "Mentorship", "Budgeting", "Cross-functional Alignment", "Python", "Cloud Platforms"],
        "borderline": ["Scrum Master", "Agile Coach", "Project Management", "Jira", "Confluence", "Stakeholder Communication", "Sprint Planning", "Kanban"],
        "reject": ["Warehouse Logistics", "Supply Chain Dispatch", "Inventory Control", "Forklift Operation"]
    }
}

PROJECT_TEMPLATES = {
    "cloud_devops": [
        ("Multi-Region EKS Platform Migration", ["Kubernetes", "EKS", "Terraform", "Helm", "ArgoCD"], [
            "Architected and deployed a multi-cluster Amazon EKS platform across 2 EU AWS regions.",
            "Standardized Helm charts and implemented GitOps deployment workflows using ArgoCD.",
            "Reduced microservice deployment lead time from 4 hours to 8 minutes with zero-downtime rolling upgrades."
        ]),
        ("Automated Infrastructure Provisioning with OpenTofu", ["Terraform", "OpenTofu", "AWS", "GitHub Actions"], [
            "Authored modular Infrastructure as Code to provision VPCs, IAM policies, and RDS databases.",
            "Integrated automated drift detection and tfsec vulnerability scanning in GitHub Actions pipelines."
        ]),
        ("Observability & Incident Telemetry Pipeline", ["Prometheus", "Grafana", "Thanos", "Loki"], [
            "Configured high-availability Prometheus monitoring with Grafana alerting rules for 120+ microservices.",
            "Established custom Service Level Indicators (SLIs) and burn rate alerts that reduced MTTR by 45%."
        ])
    ],
    "fullstack": [
        ("Next.js Enterprise Analytics Workspace", ["Next.js", "React 19", "TypeScript", "TailwindCSS"], [
            "Engineered high-performance data dashboard handling real-time tabular analytics with sub-second latency.",
            "Integrated server actions, dynamic caching, and responsive glassmorphism Dark UI components."
        ]),
        ("Distributed Microservices Backend", ["FastAPI", "Python", "PostgreSQL", "Docker", "Redis"], [
            "Designed high-throughput asynchronous REST API endpoints processing 3,500 requests per minute.",
            "Implemented Redis caching layers, connection pooling, and automated schema migrations via Alembic."
        ]),
        ("Design System & UI Component Library", ["React", "TypeScript", "Storybook", "TailwindCSS"], [
            "Authored accessible, reusable component library adhering to WCAG 2.1 AA accessibility guidelines.",
            "Accelerated feature delivery across 4 product teams by providing plug-and-play UI primitives."
        ])
    ],
    "ml_genai": [
        ("Asymmetric RAG & Vector Knowledge Engine", ["Python", "ChromaDB", "LangChain", "FastAPI"], [
            "Constructed hybrid dense-sparse RAG pipeline indexing enterprise documentation with sub-50ms query retrieval.",
            "Formulated custom re-ranking strategies and verbatim citation verification filters preventing hallucinations."
        ]),
        ("High-Throughput Open LLM Serving Gateway", ["vLLM", "Ollama", "PyTorch", "Docker"], [
            "Deployed multi-tier inference cluster hosting Llama 3.3 70B and Qwen models with automated failover.",
            "Achieved 4x throughput boost using PagedAttention and FP8 quantization while slashing GPU hosting costs."
        ]),
        ("Synthetic Evaluation & RAGAS Benchmark Suite", ["Python", "Ragas", "Pytest", "Transformers"], [
            "Developed automated test harness measuring Faithfulness, Context Precision, and Answer Relevance.",
            "Achieved a 94.2% verified factual accuracy score across 1,000 ground-truth domain queries."
        ])
    ],
    "data_eng": [
        ("Real-Time Event Streaming Lakehouse", ["Apache Spark", "Kafka", "Delta Lake", "Python"], [
            "Constructed streaming ETL ingestion processing 40 million financial events daily into Delta Lake.",
            "Eliminated downstream ingestion bottlenecks and ensured exactly-once delivery guarantees."
        ]),
        ("Modern Cloud Data Warehouse on Snowflake", ["Snowflake", "dbt", "SQL", "Airflow"], [
            "Engineered dimensional star-schema data models and orchestrated 150+ daily dbt transformation DAGs.",
            "Reduced query execution durations by 60% through aggressive clustering keys and materialized views."
        ])
    ],
    "security_appsec": [
        ("Enterprise DevSecOps & Shift-Left Pipeline", ["Trivy", "SAST", "GitHub Actions", "Docker"], [
            "Embedded automated container image scanning and static code vulnerability analysis in all PR workflows.",
            "Audited and remediated 350+ legacy dependencies, cutting critical security debt by 85%."
        ]),
        ("SOC 2 Type II & EU AI Act Governance Audit", ["ISO 27001", "SOC 2", "Threat Modeling", "Audit"], [
            "Spearheaded technical compliance verification, demographic data isolation, and cryptographic audit hashing.",
            "Authored comprehensive architectural risk management dossiers, successfully passing annual certification."
        ])
    ],
    "eng_manager": [
        ("AI Platform Engineering Transformation", ["Engineering Management", "Agile", "Architecture"], [
            "Led a high-velocity distributed engineering organization of 14 senior engineers across cloud and AI teams.",
            "Instituted DORA metrics tracking, accelerating deployment frequency by 300% and trimming change failure rate to <2%."
        ]),
        ("Core Infrastructure Re-Platforming Initiative", ["Technical Leadership", "Mentorship", "Roadmapping"], [
            "Orchestrated 18-month legacy re-platforming migration with zero customer-facing downtime.",
            "Built technical talent mentorship pathways, promoting 5 engineers into senior and staff roles."
        ])
    ]
}


def build_candidate(profile_key: str, tier: str, idx: int) -> ParsedCV:
    """Constructs a realistic, complete candidate CV structure."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    full_name = f"{first} {last}"
    email = f"{first.lower()}.{last.lower()}.{idx}@example.com"
    phone = f"+40 7{random.randint(20, 99)} {random.randint(100, 999)} {random.randint(100, 999)}"
    city = random.choice(CITIES)

    # Experience duration by tier
    if tier == "strong":
        total_years = random.randint(5, 10)
    elif tier == "borderline":
        total_years = random.randint(2, 4)
    else:  # reject
        total_years = random.randint(0, 2)

    # Skills selection
    skills_pool = PROFILE_SKILLS[profile_key][tier]
    candidate_skills = random.sample(skills_pool, k=min(len(skills_pool), random.randint(7, 12)))

    # Work experiences
    experiences: List[WorkExperience] = []
    comp_list = random.sample(COMPANIES, k=2 if total_years > 3 else 1)
    
    current_year = 2026
    start_year = current_year - total_years
    
    if tier == "strong":
        job_titles = ["Senior " + profile_key.replace("_", " ").title(), profile_key.replace("_", " ").title() + " Specialist"]
    elif tier == "borderline":
        job_titles = [profile_key.replace("_", " ").title(), "Junior " + profile_key.replace("_", " ").title()]
    else:
        job_titles = ["Junior Intern", "Support Specialist", "General Assistant"]

    for exp_idx, comp in enumerate(comp_list):
        exp_start = f"{start_year + exp_idx * 3}-03"
        exp_end = "Present" if exp_idx == len(comp_list) - 1 else f"{start_year + (exp_idx + 1) * 3}-02"
        jtitle = job_titles[min(exp_idx, len(job_titles) - 1)]
        
        # Bullets
        bullets = [
            f"Spearheaded technical development and architecture delivery at {comp}, collaborating with cross-functional teams.",
            f"Optimized operational workflows and deployed enterprise solutions utilizing {', '.join(candidate_skills[:3])}.",
            f"Mentored engineering colleagues and conducted code reviews to maintain high codebase quality standards."
        ]
        
        experiences.append(WorkExperience(
            job_title=jtitle,
            company_name=comp,
            start_date=exp_start,
            end_date=exp_end,
            duration_months=(total_years // len(comp_list)) * 12,
            work_description=bullets,
            skills_used=candidate_skills[:4],
            location=city,
            work_model="Hybrid",
            employment_type="Full-time",
            is_promotion=(exp_idx > 0)
        ))

    # Education
    uni_name, faculty = random.choice(UNIVERSITIES)
    deg_title = random.choice(DEGREES)
    grad_year = start_year - 1
    education = [
        Education(
            degree_title=deg_title,
            field_of_study=faculty,
            institution_name=uni_name,
            graduation_year=grad_year,
            gpa_or_grade=f"{random.randint(8, 10)}.{random.randint(0, 99):02d}/10",
            location=city
        )
    ]

    # Projects
    projects: List[Project] = []
    available_templates = PROJECT_TEMPLATES.get(profile_key, [])
    if available_templates:
        proj_count = 2 if tier in ("strong", "borderline") else 1
        chosen_projs = random.sample(available_templates, k=min(len(available_templates), proj_count))
        for p_name, p_stack, p_bullets in chosen_projs:
            projects.append(Project(
                project_name=f"{p_name} ({tier.upper()} Tier)",
                description=p_bullets,
                technologies=p_stack,
                start_date=f"{current_year - 2}-01",
                end_date=f"{current_year - 1}-11",
                project_url=f"https://github.com/{first.lower()}{last.lower()}/{p_name.lower().replace(' ', '-')}"
            ))

    # Languages
    languages = [
        LanguageSkill(language="English", proficiency="C1 - Professional Working"),
        LanguageSkill(language="Romanian", proficiency="Native")
    ]
    if random.random() > 0.6:
        languages.append(LanguageSkill(language="French", proficiency="B1 - Intermediate"))

    # Raw CV text (simulating real resume document)
    raw_text = f"""
CURRICULUM VITAE

{full_name}
Email: {email} | Phone: {phone}
Location: {city} | LinkedIn: https://linkedin.com/in/{first.lower()}-{last.lower()}
GitHub: https://github.com/{first.lower()}{last.lower()}

PROFESSIONAL SUMMARY
Results-driven engineering professional with {total_years} years of demonstrated experience in {profile_key.replace('_', ' ').title()}.
Core expertise includes {', '.join(candidate_skills[:6])}. Strong background in scalable architectures, automated delivery, and team collaboration.

CORE SKILLS & TECHNOLOGIES
{', '.join(candidate_skills)}

PROFESSIONAL EXPERIENCE
"""
    for exp in experiences:
        raw_text += f"\n{exp.job_title} | {exp.company_name} ({exp.start_date} - {exp.end_date})\n"
        for b in exp.work_description:
            raw_text += f"• {b}\n"

    raw_text += "\nTECHNICAL PROJECTS & PORTFOLIO\n"
    for p in projects:
        raw_text += f"\nProject: {p.project_name}\nTechnologies: {', '.join(p.technologies)}\n"
        for pb in p.description:
            raw_text += f"• {pb}\n"

    raw_text += f"\nEDUCATION\n{education[0].degree_title} - {education[0].institution_name} ({education[0].graduation_year})\nMajor: {education[0].field_of_study}\n"

    parsed = ParsedCV(
        contact_info=ContactInfo(
            full_name=full_name,
            email=email,
            phone_number=phone,
            location=city,
            linkedin_url=f"https://linkedin.com/in/{first.lower()}-{last.lower()}",
            github_url=f"https://github.com/{first.lower()}{last.lower()}"
        ),
        summary=f"Experienced {profile_key.replace('_', ' ').title()} specialist with {total_years}+ years of expertise.",
        skills=candidate_skills,
        experiences=experiences,
        education=education,
        certifications=[f"Certified {candidate_skills[0]} Specialist"],
        projects=projects,
        languages=languages,
        raw_text=raw_text.strip()
    )
    return parsed


async def seed_cohort(total_count: int = 300):
    print("=" * 70)
    print(f"Generating & Seeding {total_count} Synthetic Candidates (SQLite + ChromaDB)")
    print("=" * 70)

    scrubber = PIIScrubber()
    vector_store = VectorStoreService()

    # Proportions: 35% Strong, 30% Borderline, 35% Reject
    strong_target = int(total_count * 0.35)
    borderline_target = int(total_count * 0.30)
    reject_target = total_count - strong_target - borderline_target

    targets = [("strong", strong_target), ("borderline", borderline_target), ("reject", reject_target)]
    
    generated_count = 0
    total_chunks = 0

    start_time = datetime.now()

    for tier, count in targets:
        print(f"\n---> Generating {count} candidates for tier [{tier.upper()}]...")
        for i in range(count):
            profile = ROLES_PROFILES[generated_count % len(ROLES_PROFILES)]
            parsed_cv = build_candidate(profile, tier, generated_count + 1)
            
            # Anonymize & Scrub PII (EU AI Act Compliance)
            anonymized = scrubber.anonymize_cv(parsed_cv)
            anonymized.candidate_id = str(uuid.uuid4())

            # Index in ChromaDB
            chunks = vector_store.index_candidate(anonymized, force=True)
            total_chunks += chunks

            # Save in SQLite Relational DB
            filename = f"{anonymized.candidate_id[:8]}_{profile}_{tier}.json"
            await DatabaseRepository.save_candidate(
                parsed_cv=parsed_cv,
                anonymized_candidate=anonymized,
                chunks_indexed=chunks,
                filename=filename
            )

            generated_count += 1
            if generated_count % 50 == 0 or generated_count == total_count:
                print(f"  [Progress] {generated_count}/{total_count} candidates indexed ({total_chunks} vector chunks)...")

    duration = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 70)
    print(f"SUCCESS: Successfully generated and indexed {generated_count} candidates in {duration:.1f}s.")
    print(f"Total vector chunks indexed in ChromaDB: {total_chunks}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_cohort(300))

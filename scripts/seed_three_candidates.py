"""
scripts/seed_three_candidates.py
Seeds the 3 ideal fictional candidates tailored to specific job postings:
1. Camille Beaumont (Atos - Bid Manager with French)
2. Nguyen Minh Khoa (FORVIA HELLA - Embedded SW Engineer RS2)
3. Tyler James Kowalski (Magna - Material Handler)
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from backend.schemas.cv import (
    ContactInfo, CustomSection, Education, LanguageSkill, LogisticalInfo,
    ParsedCV, Project, WorkExperience,
)
from backend.services.pii_scrubber import PIIScrubber
from backend.services.vector_store import VectorStoreService
from backend.db.repository import DatabaseRepository


def build_atos_bid_manager() -> ParsedCV:
    return ParsedCV(
        contact_info=ContactInfo(
            full_name="Camille Beaumont",
            email="camille.beaumont.bm@atos-career.eu",
            phone_number="+40 756 100 200",
            location="Timisoara, Romania",
            linkedin_url="https://linkedin.com/in/camille-beaumont-bid",
        ),
        summary=(
            "Senior Bid Manager with 8+ years of experience orchestrating complex IT services proposals "
            "across France, DACH, and Benelux markets for Tier-1 digital services providers. "
            "Expert in sales excellence methodologies, Rainbow governance, Salesforce CRM, and Price-to-Win strategies. "
            "Bilingual French-English communicator with a track record of >40% win rate on pursuits below €25M, "
            "leading multi-disciplinary teams of Presales, Finance, Legal, and Delivery stakeholders."
        ),
        skills=[
            "Bid Management", "Proposal Writing", "Rainbow Governance", "Sales Excellence Methodology",
            "Salesforce CRM", "Price-to-Win Strategy", "Competitive Analysis", "Stakeholder Alignment",
            "Program Management", "Risk & Compliance Management", "Document Control",
            "Contract Negotiation", "Microsoft Office 365", "SharePoint", "Jira", "Confluence",
            "IT Services", "Cloud Services", "Digital Transformation", "Outsourcing",
            "Pre-Sales Support", "Win/Loss Analysis", "Cost of Sale Optimization", "Agile / Scrum",
        ],
        experiences=[
            WorkExperience(
                job_title="Senior Bid Manager",
                company_name="Eviden (formerly Atos)",
                location="Timisoara, Romania",
                start_date="January 2022",
                end_date="Present",
                work_model="Hybrid",
                employment_type="Full-time",
                work_description=[
                    "Led 35+ bids below €25M for French public sector and enterprise clients, achieving a 44% win rate YoY.",
                    "Applied Rainbow governance framework end-to-end: qualification gates, bid/no-bid decisions, proposal reviews, and final submission quality audits.",
                    "Orchestrated cross-functional bid teams of 8–15 members (Presales, Finance, Legal, Delivery, Security) and coordinated with external partners.",
                    "Maintained Salesforce CRM pipeline hygiene, opportunity qualification, and milestone reporting for senior leadership.",
                    "Integrated competitive analysis and Price-to-Win benchmarking into bid strategies, reducing average cost of sale by 18%.",
                    "Captured and reused proposal assets, building a reusable bid library that cut first-draft production time by 30%.",
                ],
                skills_used=["Bid Management", "Rainbow Governance", "Salesforce CRM", "Price-to-Win", "Stakeholder Alignment", "Proposal Writing"],
            ),
            WorkExperience(
                job_title="Bid Coordinator / Junior Bid Manager",
                company_name="Capgemini Romania",
                location="Timisoara, Romania",
                start_date="March 2019",
                end_date="December 2021",
                work_model="On-site",
                employment_type="Full-time",
                work_description=[
                    "Supported senior bid managers on RFP/RFI/ITT responses for French-speaking clients in Banking and Insurance sectors.",
                    "Coordinated proposal logistics: content gathering, version control, translation review (FR/EN), and final submission packaging.",
                    "Managed internal bid portals and document repositories in SharePoint, ensuring compliance with bid process requirements.",
                    "Tracked bid calendars, resource availability, and external partner contributions across 10+ simultaneous pursuits.",
                    "Conducted post-bid debriefs and win/loss analysis, contributing to continuous improvement of the bid methodology.",
                ],
                skills_used=["Proposal Coordination", "SharePoint", "Document Control", "Win/Loss Analysis", "French", "RFP Response"],
            ),
            WorkExperience(
                job_title="Presales Support Analyst",
                company_name="Orange Business Services",
                location="Paris, France",
                start_date="September 2016",
                end_date="February 2019",
                work_model="On-site",
                employment_type="Full-time",
                work_description=[
                    "Provided presales support for enterprise telecom and managed services bids across French accounts.",
                    "Prepared technical and commercial annexes, compliance matrices, and executive summaries for client presentations.",
                    "Coordinated with legal and finance teams on pricing models and contractual terms for multi-year managed services contracts.",
                ],
                skills_used=["Presales Support", "Technical Writing", "Compliance Matrices", "Pricing Models", "Telecom Services"],
            ),
        ],
        education=[
            Education(
                degree_title="Master of Science in Business Management & Digital Transformation",
                institution_name="EDHEC Business School",
                graduation_year=2016,
                location="Lille, France",
            ),
            Education(
                degree_title="Bachelor of Arts in Applied Languages — English & Romanian",
                institution_name="Université de Strasbourg",
                graduation_year=2014,
                location="Strasbourg, France",
            ),
        ],
        certifications=[
            "APMP Foundation — Association of Proposal Management Professionals",
            "Salesforce Certified Administrator (SCA)",
            "Prince2 Foundation",
            "Microsoft Certified: Azure Fundamentals (AZ-900)",
        ],
        languages=[
            LanguageSkill(language="French", proficiency="Native (C2)"),
            LanguageSkill(language="English", proficiency="Bilingual / Fluent (C1)"),
            LanguageSkill(language="Romanian", proficiency="Professional Working (B2)"),
        ],
        projects=[
            Project(
                project_name="€18M Managed Cloud Services Rebid — French Ministry of Finance",
                description=[
                    "Led a 90-day complex rebid effort for a €18M 5-year managed cloud and cybersecurity services contract.",
                    "Coordinated a 12-person bid team across France, Romania, and India; delivered a fully compliant, on-time proposal.",
                    "Won the contract, representing the largest single win for the Timisoara bid centre in 2023.",
                ],
                technologies=["Salesforce CRM", "SharePoint", "Rainbow Governance", "Price-to-Win"],
            ),
        ],
        logistics=LogisticalInfo(
            notice_period="1 month",
            relocation_preference="Open to EU relocation",
            work_authorization="EU Citizen — Romanian residence permit",
        ),
        raw_text="Camille Beaumont | Senior Bid Manager with French | Timisoara, Romania | camille.beaumont.bm@atos-career.eu",
    )


def build_hella_embedded_engineer() -> ParsedCV:
    return ParsedCV(
        contact_info=ContactInfo(
            full_name="Nguyen Minh Khoa",
            email="minhkhoa.nguyen.sw@hella-dev.vn",
            phone_number="+84 90 123 4567",
            location="Ho Chi Minh City, Vietnam",
            linkedin_url="https://linkedin.com/in/nguyen-minh-khoa-adas",
            github_url="https://github.com/minhkhoa-embedded",
        ),
        summary=(
            "Embedded Software Engineer with 3+ years of experience in automotive ADAS and autonomous driving systems. "
            "Proficient in C/C++ on 32-bit MCUs (Infineon TriCore), AUTOSAR Classic, and the full ASPICE SWE lifecycle. "
            "Strong background in Radar sensor firmware, CAN/LIN/Ethernet communication stacks, and functional safety (ISO 26262 ASIL-B). "
            "Experienced with embedded toolchains: Rhapsody, Polyspace, DaVinci, Vector CANoe, and DOORS."
        ),
        skills=[
            "C", "C++", "CAPL", "Embedded C", "AUTOSAR Classic",
            "Infineon TriCore MCU", "32-bit MCU Development", "Bare Metal / RTOS", "Multi-core Development",
            "IBM Rhapsody (Rational Rhapsody)", "Polyspace Bug Finder", "WindIdea", "DaVinci Configurator", "IBM DOORS",
            "Vector CANoe", "Vector CANdb++", "PTC Integrity",
            "CAN", "LIN", "Ethernet", "TCP/IP", "J1939", "UDS (ISO 14229)",
            "ASPICE SWE.1–SWE.6", "ISO 26262 Functional Safety (ASIL-B)", "MISRA C:2012",
            "Radar ADAS", "Autonomous Driving", "FBL / Bootloader SW",
            "CI/CD (Jenkins)", "Git", "Python (test automation)", "Unit Testing (VectorCAST)",
            "Cybersecurity (EVITA)", "Secure Boot", "Agile / Scrum",
        ],
        experiences=[
            WorkExperience(
                job_title="Embedded Software Engineer — ADAS Radar",
                company_name="FORVIA HELLA Vietnam",
                location="Ho Chi Minh City, Vietnam",
                start_date="July 2023",
                end_date="Present",
                work_model="On-site",
                employment_type="Full-time",
                work_description=[
                    "Primarily responsible for software modules of HELLA's 77 GHz Radar ADAS product line targeting Level 2+ autonomous driving.",
                    "Implemented and maintained AUTOSAR-compliant SWCs for radar signal processing, object detection, and CAN FD communication on Infineon TriCore TC397 MCU.",
                    "Led high-level collaborative design of integrated solutions in compliance with ASPICE SWE.1–SWE.6 across 3 active radar platform projects.",
                    "Worked with Software Project Manager to identify optimal technical solutions for RADAR-to-ECU interface challenges, cutting integration defects by 25%.",
                    "Conducted design quality reviews and provided mentorship to 2 junior engineers on Rhapsody modeling and MISRA C compliance.",
                    "Implemented UDS diagnostic services (0x22, 0x2E, 0x31, 0x36) and Flashbootloader (FBL) modules aligned with OEM specifications.",
                    "Integrated cybersecurity measures (EVITA Medium, Secure Boot) into the BSW layer in compliance with ISO 21434.",
                ],
                skills_used=["C", "AUTOSAR Classic", "Infineon TriCore TC397", "Rhapsody", "DaVinci Configurator", "CAN FD", "UDS", "FBL", "ASPICE", "ISO 26262 ASIL-B", "Vector CANoe", "MISRA C:2012"],
            ),
            WorkExperience(
                job_title="Junior Embedded Software Engineer",
                company_name="Renesas Design Vietnam",
                location="Ho Chi Minh City, Vietnam",
                start_date="August 2021",
                end_date="June 2023",
                work_model="On-site",
                employment_type="Full-time",
                work_description=[
                    "Developed and unit-tested bare-metal C drivers for Renesas RH850 MCU peripherals (SPI, UART, CAN, LIN) for body electronics ECUs.",
                    "Used Polyspace Bug Finder and VectorCAST to achieve MISRA C compliance and unit test coverage targets of 95%+.",
                    "Participated in LIN cluster driver integration and regression testing using Vector CANoe with CAPL scripting.",
                    "Maintained DOORS traceability matrices linking requirements to design artifacts for ASPICE SWE.4 evidence.",
                    "Contributed to CI pipeline (Jenkins + Git) for automated build, static analysis, and test execution.",
                ],
                skills_used=["C", "Renesas RH850 MCU", "SPI", "UART", "CAN", "LIN", "Polyspace", "VectorCAST", "Vector CANoe", "CAPL", "DOORS", "ASPICE", "Jenkins", "Git"],
            ),
        ],
        education=[
            Education(
                degree_title="Bachelor of Engineering in Computer Engineering",
                institution_name="Ho Chi Minh City University of Technology (HCMUT)",
                graduation_year=2021,
                location="Ho Chi Minh City, Vietnam",
                gpa_or_grade="3.6/4.0",
                honors="Top 10% of graduating cohort",
            ),
        ],
        certifications=[
            "ISO 26262 Functional Safety Engineer (TUV SUD — ASIL-B Certified)",
            "Vector Academy — CANoe Advanced CAPL Scripting",
            "AUTOSAR Training — Vector Academy (Classic Platform)",
        ],
        languages=[
            LanguageSkill(language="English", proficiency="Fluent (C1)"),
            LanguageSkill(language="Vietnamese", proficiency="Native (C2)"),
        ],
        projects=[
            Project(
                project_name="HELLA 77 GHz Radar — FBL & OTA Update Module",
                description=[
                    "Designed and implemented a AUTOSAR-compliant Flashbootloader and OTA Software Update Manager for the HELLA Radar ECU.",
                    "Integrated UDS 0x34/0x36/0x37 data transfer services with CRC validation and rollback on checksum failure.",
                    "Passed OEM OTA acceptance testing on first submission with zero critical defects.",
                ],
                technologies=["C", "AUTOSAR Classic", "UDS", "CAN FD", "Infineon TriCore TC397", "DaVinci Configurator"],
            ),
        ],
        logistics=LogisticalInfo(
            notice_period="2 months",
            work_authorization="Vietnamese Citizen — Vietnam work authorization",
        ),
        raw_text="Nguyen Minh Khoa | Embedded SW Engineer ADAS | Ho Chi Minh City, Vietnam | minhkhoa.nguyen.sw@hella-dev.vn",
    )


def build_magna_material_handler() -> ParsedCV:
    return ParsedCV(
        contact_info=ContactInfo(
            full_name="Tyler James Kowalski",
            email="tyler.kowalski.wh@magnajobs.us",
            phone_number="+1 (480) 555-0192",
            location="Mesa, AZ, USA",
            linkedin_url="https://linkedin.com/in/tyler-kowalski-warehouse",
        ),
        summary=(
            "Reliable and safety-conscious Warehouse Associate with 2+ years of material handling experience "
            "in a high-volume automotive manufacturing environment. Certified forklift operator (sit-down and reach truck) "
            "with hands-on SAP WM experience for inventory transactions and replenishment requests. "
            "Strong track record of maintaining 5S standards, PPE compliance, and zero lost-time safety incidents. "
            "Physically capable of lifting 50+ lbs with a consistent attendance record and team-first attitude."
        ),
        skills=[
            "Material Handling", "Forklift Operation (Sit-Down & Reach Truck)", "SAP WM (Tablet-Based)",
            "Inventory Management", "5S Methodology", "Warehouse Safety / PPE Compliance",
            "Pick, Pack & Stage", "Bin Replenishment", "Shipping & Receiving",
            "Barcode Scanning", "FIFO / FEFO Inventory", "Production Line Feeding",
            "Daily Equipment Inspection", "Cross-Docking", "RF Scanner Operation",
            "Teamwork", "Attention to Detail", "Time Management", "Communication",
        ],
        experiences=[
            WorkExperience(
                job_title="Warehouse Material Handler / Forklift Operator",
                company_name="Magna International — Cosma Body & Assembly",
                location="Mesa, AZ, USA",
                start_date="March 2024",
                end_date="Present",
                work_model="On-site",
                employment_type="Full-time",
                work_description=[
                    "Receive, unload, verify, label, and pack incoming stamped metal components and outgoing sub-assemblies for Tier-1 automotive customer deliveries.",
                    "Use SAP WM (tablet-based) to process inventory transactions: goods receipt, stock transfers, replenishment requests, and shipping activities with 99.8%+ accuracy rate.",
                    "Operate sit-down counterbalance and reach forklift safely across 3 warehouse zones; complete daily pre-shift equipment inspections.",
                    "Stock, put-away, replenish, pick, and stage materials in designated rack locations and production line flow racks at 6am shift start.",
                    "Support production line feeding by coordinating with manufacturing supervisors to eliminate material shortages and minimize downtime.",
                    "Maintain 5S standards in all assigned warehouse areas; recognized as 5S Champion for Q3 2024 with zero audit findings.",
                    "Achieved zero lost-time safety incidents across 18 months on the floor; consistently follow PPE requirements and safety protocols.",
                ],
                skills_used=["SAP WM", "Forklift Operation", "5S", "Inventory Management", "Pick/Pack/Stage", "Production Line Feeding", "Material Handling"],
            ),
            WorkExperience(
                job_title="Warehouse Associate",
                company_name="Amazon Fulfillment Center — PHX3",
                location="Chandler, AZ, USA",
                start_date="June 2023",
                end_date="February 2024",
                work_model="On-site",
                employment_type="Full-time",
                work_description=[
                    "Performed inbound receiving, stowing, picking, packing, and shipping operations in a 1.2M sq ft fulfillment center.",
                    "Used handheld RF scanner and warehouse management system to maintain real-time inventory accuracy targets of 99.5%+.",
                    "Consistently met and exceeded pick rate productivity targets (350+ units/hour) while maintaining quality and safety standards.",
                    "Completed safety walkthroughs and hazard reporting; maintained a clean and organized workstation at all times.",
                ],
                skills_used=["RF Scanner", "Warehouse Management System", "Pick/Pack/Ship", "Inventory Accuracy", "Safety Compliance"],
            ),
        ],
        education=[
            Education(
                degree_title="High School Diploma",
                institution_name="Mesa High School",
                graduation_year=2022,
                location="Mesa, AZ, USA",
            ),
        ],
        certifications=[
            "OSHA 10-Hour General Industry Safety Certification",
            "Certified Forklift Operator — Sit-Down Counterbalance (Toyota 8FGCU25)",
            "Certified Forklift Operator — Reach Truck (Crown RR 5700)",
            "SAP WM Essentials — Magna Internal Training Certificate",
        ],
        languages=[
            LanguageSkill(language="English", proficiency="Native (C2)"),
            LanguageSkill(language="Spanish", proficiency="Basic (A2)"),
        ],
        projects=[
            Project(
                project_name="5S Overhaul — Magna Mesa Receiving Dock",
                description=[
                    "Led a 2-week 5S improvement project on the inbound receiving dock, reorganizing rack labeling, visual flow indicators, and overflow staging areas.",
                    "Reduced average goods receipt processing time by 22% by reorganizing dock-to-shelf workflow and introducing shadow board tooling.",
                    "Project selected as a site best practice and replicated across two additional warehouse zones.",
                ],
                technologies=["5S Methodology", "SAP WM", "Kaizen", "Visual Management"],
            ),
        ],
        logistics=LogisticalInfo(
            notice_period="2 weeks",
            work_authorization="US Citizen",
            travel_willingness="None",
        ),
        custom_sections=[
            CustomSection(
                section_title="Physical Capability",
                items=[
                    "Ability to lift up to 55 lbs repeatedly throughout shift",
                    "Comfortable with prolonged standing (8+ hours), frequent bending, squatting, and reaching",
                    "Available Mon–Fri, 6am–2:30pm shift (Magna Mesa schedule)",
                ],
            ),
        ],
        raw_text="Tyler James Kowalski | Warehouse Material Handler | Mesa, AZ, USA | tyler.kowalski.wh@magnajobs.us",
    )


async def main():
    scrubber = PIIScrubber()
    vector_store = VectorStoreService()

    candidates = [
        (build_atos_bid_manager(),        "camille.beaumont.bm@atos-career.eu",          "camille_beaumont_bid_manager_atos.txt"),
        (build_hella_embedded_engineer(), "minhkhoa.nguyen.sw@hella-dev.vn",             "nguyen_minh_khoa_hella_embedded_sw.txt"),
        (build_magna_material_handler(),  "tyler.kowalski.wh@magnajobs.us",              "tyler_kowalski_magna_material_handler.txt"),
    ]

    for parsed_cv, seed_email, filename in candidates:
        filepath = Path("data/mock_cvs") / filename
        if filepath.exists():
            parsed_cv.raw_text = filepath.read_text(encoding="utf-8")
        name = parsed_cv.contact_info.full_name
        fixed_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, seed_email)
        anonymized = scrubber.anonymize_cv(parsed_cv)
        anonymized.candidate_id = fixed_uuid
        chunks = vector_store.index_candidate(anonymized, force=True)
        saved = await DatabaseRepository.save_candidate(
            parsed_cv=parsed_cv,
            anonymized_candidate=anonymized,
            chunks_indexed=chunks,
            filename=filename,
        )
        print(f"Candidate: {name:<25} | ID: {saved.id} | Chunks: {chunks} | Raw text len: {len(parsed_cv.raw_text)} | Sanitized len: {len(anonymized.sanitized_text)}")


if __name__ == "__main__":
    asyncio.run(main())

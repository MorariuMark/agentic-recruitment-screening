"""
scripts/seed_marcus_vance.py
Seeds candidate MARCUS VANCE into SQLite (data/screening.db) and ChromaDB (data/chroma_db).
"""

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import uuid

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.models import CandidateModel
from backend.db.repository import DatabaseRepository
from backend.schemas.cv import (
    ContactInfo,
    CustomSection,
    Education,
    LanguageSkill,
    LogisticalInfo,
    ParsedCV,
    Project,
    WorkExperience,
)
from backend.services.pii_scrubber import PIIScrubber
from backend.services.vector_store import VectorStoreService


def build_marcus_vance_cv() -> ParsedCV:
    raw_text = Path("data/mock_cvs/marcus_vance_embedded_systems_engineer.txt").read_text(encoding="utf-8")

    contact = ContactInfo(
        full_name="Marcus Vance",
        email="marcus.vance.dev@email.com",
        phone_number="+49 170 000 0000",
        location="Hanover, Germany / Remote",
        linkedin_url="https://linkedin.com/in/marcus-vance",
        github_url="https://github.com/marcusvance",
    )

    summary = (
        "Embedded Systems and Software Engineer with 4+ years of experience designing firmware, "
        "telemetry pipelines, and low-power sensor networks for connected automotive and industrial systems. "
        "Proven expertise integrating edge data acquisition with CAN bus networks and cloud-connected telematics platforms. "
        "Deep background in C/C++, FreeRTOS, BLE/RF, and Python data pipelines aligned with automotive reliability "
        "and ISO 26262/ASPICE process environments."
    )

    skills = [
        "C", "Modern C++ (C++17/20)", "Python", "Embedded Linux", "FreeRTOS", "Zephyr RTOS", "POSIX",
        "ARM Cortex-M0+", "ARM Cortex-M4", "ARM Cortex-M33", "STM32", "NRF52/53 series", "ESP32", "TI SimpleLink", "Edge TPU",
        "CAN 2.0B", "CAN FD", "LIN", "SPI", "I2C", "UART", "Modbus",
        "BLE 5.x", "Bluetooth Mesh", "MQTT", "HTTP/REST", "CoAP", "LoRaWAN", "Protobuf",
        "Saleae Logic Analyzers", "Rohde & Schwarz Oscilloscopes", "Vector CANoe (Basic)", "J-Link", "Git", "CMake", "Docker", "CI/CD (GitHub Actions)",
        "ASPICE", "ISO 26262 (Functional Safety awareness)", "MISRA C/C++", "Agile / Scrum",
        "TPMS", "TMS", "Hardware-in-the-Loop (HIL)", "PyVISA", "MEMS Accelerometers", "Energy Harvesting", "Power Management",
        "Wear Leveling", "Flash Logging", "EdgeML", "TensorFlow Lite for Microcontrollers", "J1939"
    ]

    experiences = [
        WorkExperience(
            job_title="Embedded Systems Software Engineer",
            company_name="Sensata Technologies",
            location="Hanover, Germany",
            start_date="March 2024",
            end_date="Present",
            work_model="Hybrid",
            employment_type="Full-time",
            work_description=[
                "Architected and maintained ultra-low-power C firmware for smart tire pressure and temperature monitoring systems (TPMS/TMS) operating on ARM Cortex-M33 platforms.",
                "Designed an event-driven energy-harvesting power management scheme, cutting quiescent current draw to < 2.1 µA and extending in-tire battery longevity past 6 years.",
                "Integrated custom SPI/I2C drivers for high-g MEMS accelerometers to detect rotational frequency, tread deformation patterns, and vehicle loading state.",
                "Collaborated with global telematics teams across Germany and Portugal to standardize tire data serialization over Bluetooth Low Energy (BLE) and CAN FD gateways.",
                "Established an automated hardware-in-the-loop (HIL) regression suite with Python and PyVISA, shortening firmware release validation cycles from 4 days to 6 hours.",
            ],
            skills_used=["C", "ARM Cortex-M33", "TPMS", "TMS", "SPI", "I2C", "MEMS Accelerometers", "BLE", "CAN FD", "Python", "PyVISA", "HIL", "Power Management"],
        ),
        WorkExperience(
            job_title="Junior Firmware & Telematics Developer",
            company_name="ACTIA Nordic",
            location="Malmö, Sweden",
            start_date="August 2022",
            end_date="February 2024",
            work_model="On-site",
            employment_type="Full-time",
            work_description=[
                "Implemented low-level sensor drivers and protocol stacks in C for commercial vehicle telematic gateway units (TGUs).",
                "Engineered a robust circular flash logging algorithm with wear leveling for offline vehicle telemetry, buffering up to 100,000 driving events during cellular outages.",
                "Implemented MISRA-C:2012 compliance checks into the Jenkins CI pipeline, cutting static analysis defect rates by 38% prior to QA handoff.",
                "Participated in sprint planning, sprint retrospectives, and cross-functional peer reviews within an ASPICE Level 2 certified workflow.",
            ],
            skills_used=["C", "Telematics Gateway Units (TGUs)", "Flash Logging", "Wear Leveling", "MISRA-C:2012", "Jenkins CI", "ASPICE Level 2", "Agile / Scrum"],
        ),
        WorkExperience(
            job_title="Working Student / Embedded Software Intern",
            company_name="Continental Tires R&D",
            location="Hanover, Germany",
            start_date="October 2021",
            end_date="July 2022",
            work_model="On-site",
            employment_type="Working Student",
            work_description=[
                "Built an internal diagnostic dashboard in Python (Flask, Dash) to visualize live CAN and BLE telemetry from test vehicles equipped with developmental sensorized tires.",
                "Assisted senior systems engineers with RF field-testing, measuring signal attenuation through heavy-duty rubber compounds across multiple rim configurations.",
                "Created reproducible automated unit tests using Ceedling/Unity for bare-metal microcontroller routines.",
            ],
            skills_used=["Python", "Flask", "Dash", "CAN", "BLE", "Ceedling", "Unity", "Bare-metal Microcontrollers", "RF Field Testing"],
        ),
    ]

    education = [
        Education(
            degree_title="Master of Science in Embedded & Cyber-Physical Systems",
            institution_name="Leibniz University Hannover, Germany",
            graduation_year=2023,
            thesis_title="Dynamic Tire-Road Interaction Modeling via Edge-Processed Triaxial MEMS Accelerometers",
            location="Hanover, Germany",
        ),
        Education(
            degree_title="Bachelor of Science in Electrical and Computer Engineering",
            institution_name="Technical University of Munich (TUM), Germany",
            graduation_year=2021,
            location="Munich, Germany",
        ),
    ]

    projects = [
        Project(
            project_name="EdgeML Predictive Tire Wear Estimator",
            technologies=["C++", "TensorFlow Lite for Microcontrollers", "Python"],
            description=[
                "Trained a 1D-CNN using accelerometer datasets to predict tire surface degradation and tread depth within 0.4 mm error margins.",
                "Quantized the neural net to int8 precision and executed inference on an nRF52840 SoC with sub-18 ms execution times and minimal memory footprint (< 24 KB RAM).",
            ],
        ),
        Project(
            project_name="Distributed CAN FD Sensor Gateway",
            technologies=["C", "FreeRTOS", "STM32", "Ethernet", "MQTT"],
            description=[
                "Built a multi-channel CAN FD to Ethernet gateway processing up to 4,000 frames/sec without buffer overruns, parsing incoming J1939 messages and streaming telemetry over MQTT.",
            ],
        ),
    ]

    languages = [
        LanguageSkill(language="English", proficiency="Bilingual / Fluent (C2)"),
        LanguageSkill(language="German", proficiency="Professional Working (C1)"),
    ]

    certifications = [
        "Certified Functional Safety Specialist (ISO 26262 Overview)",
        "Professional Scrum Developer I (PSD I)",
    ]

    logistics = LogisticalInfo(
        relocation_preference="Hanover, Germany or Remote",
        work_authorization="EU / Germany Work Authorization",
    )

    custom_sections = [
        CustomSection(
            section_title="Why This CV Hits Every Note of the JD",
            items=[
                "Intelligent Tire Systems & Sensors: Direct experience in TPMS, tread/wear tracking, and low-power in-tire electronics.",
                "Integrated Hardware & Software: Bare-metal C/C++, ARM Cortex-M, MEMS sensor integration, and RTOS scheduling.",
                "Vehicle Integration & Networks: CAN 2.0B / CAN FD, LIN, BLE 5.x, telematics gateways, and MQTT streaming.",
                "Global / Agile Culture: Cross-site collaboration, Scrum/Agile methodology, and ASPICE process familiarity.",
                "Working Student to Career Path: Features a Working Student background matching Continental's standard entry framework.",
            ],
        )
    ]

    return ParsedCV(
        contact_info=contact,
        summary=summary,
        skills=skills,
        experiences=experiences,
        education=education,
        certifications=certifications,
        projects=projects,
        languages=languages,
        logistics=logistics,
        custom_sections=custom_sections,
        raw_text=raw_text,
    )


async def main():
    print("Building parsed CV for Marcus Vance...")
    parsed_cv = build_marcus_vance_cv()

    # Deterministic UUID based on email so rerun is idempotent
    fixed_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, "marcus.vance.dev@email.com")

    # Scrub PII
    scrubber = PIIScrubber()
    anonymized = scrubber.anonymize_cv(parsed_cv)
    anonymized.candidate_id = fixed_uuid

    print(f"Candidate UUID: {anonymized.candidate_id}")

    # Vector store indexing
    print("Indexing candidate in ChromaDB...")
    vector_store = VectorStoreService()
    chunks = vector_store.index_candidate(anonymized, force=True)
    print(f"Chunks indexed in ChromaDB: {chunks}")

    # Database persistence
    filename = "marcus_vance_embedded_systems_engineer.txt"
    print(f"Saving candidate to database (filename: {filename})...")
    saved_cand = await DatabaseRepository.save_candidate(
        parsed_cv=parsed_cv,
        anonymized_candidate=anonymized,
        chunks_indexed=chunks,
        filename=filename,
    )
    print(f"Successfully saved candidate record in database: ID={saved_cand.id}, Name={saved_cand.full_name_redacted}")

    # Verify retrieval
    retrieved = await DatabaseRepository.get_candidate(fixed_uuid)
    assert retrieved is not None, "Failed to retrieve candidate from database"
    assert retrieved.full_name_redacted == "Marcus Vance", f"Expected Marcus Vance, got {retrieved.full_name_redacted}"
    print("Verification passed! Marcus Vance is successfully stored in the database.")


if __name__ == "__main__":
    asyncio.run(main())

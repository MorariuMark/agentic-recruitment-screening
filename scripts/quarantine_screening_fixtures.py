"""Move confirmed historical test profiles to demo data, preserving audit history.

Defaults to a dry run. --apply creates a SQLite backup before any updates.
Names alone never establish provenance: filename, contact, skills, work text,
and the absence of original CV text must all match the repository fixtures.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine import make_url
from backend.config import settings


FIXTURES = {
    "alex_cv.txt": ("Alex Wright", "alex@example.com", ["Python", "FastAPI"], ["Alex Wright engineered RAG pipelines with Python."]),
    "sarah_cv.txt": ("Sarah Connor", "sarah@resistance.ai", ["Python", "FastAPI", "Cybersecurity"], ["Defended distributed systems against unauthorized access."]),
    "bruce_cv.pdf": ("Bruce Wayne", "bruce@wayne-enterprises.com", ["Python", "FastAPI", "Kubernetes"], ["Built high-throughput RAG search with FastAPI and ChromaDB."]),
    "clark_cv_1.txt": ("Clark Kent", "clark@dailyplanet.com", ["Python"], []),
    "clark_cv_2.txt": ("Clark Kent", "clark@dailyplanet.com", ["Python"], []),
    "alice_cv.pdf": ("Alice Smith", "alice@test.com", ["Kubernetes", "Go"], []),
    "bob_cv.pdf": ("Bob Jones", "bob@test.com", ["Go"], []),
    "elena_rostova_cv.pdf": ("Elena Rostova", "elena.rostova@example.com", ["SIEM", "Splunk", "Incident Handling", "Forensics"], ["Orchestrated enterprise SOC incident response drills across 500+ endpoints"]),
}


def is_fixture(filename, raw, anonymized, source):
    if source.strip() or (anonymized.get("sanitized_text") or "").strip() or filename not in FIXTURES:
        return False
    contact = raw.get("contact_info") or {}
    signature = (contact.get("full_name"), contact.get("email"), raw.get("skills", []),
                 [bullet for role in raw.get("experiences", []) for bullet in role.get("work_description", [])])
    return signature == FIXTURES[filename]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        parser.error("This historical repair supports the configured SQLite database only.")
    path = Path(url.database).resolve(strict=True)
    connection = sqlite3.connect(path)
    updates = []
    for cid, filename, raw_json, anon_json, source in connection.execute(
        "SELECT id, original_filename, raw_cv_json, anonymized_cv_json, sanitized_text FROM candidates"):
        raw, anon = json.loads(raw_json), json.loads(anon_json)
        if raw.get("dataset") != "benchmark" and is_fixture(filename, raw, anon, source):
            updates.append((cid, raw, anon))
    jobs = []
    for jid, title, source in connection.execute("SELECT id, title, raw_text FROM job_requisitions WHERE title='AI Engineer'"):
        requirements = connection.execute("SELECT id, title, description, category, weight FROM job_requirements WHERE job_id=?", (jid,)).fetchall()
        if not (source or "").strip() and requirements == [("req_fastapi", "FastAPI", "FastAPI REST microservices", "must_have", 1.0)]:
            jobs.append((jid, title))
    print(f"Confirmed test profiles to move to demo: {len(updates)}; exact test jobs to label: {len(jobs)}")
    if args.apply and (updates or jobs):
        backup = path.parent / "backups" / f"before-fixture-quarantine-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.db"
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as target:
            connection.backup(target)
        with connection:
            for cid, raw, anon in updates:
                for profile in (raw, anon):
                    profile["dataset"] = "benchmark"
                    profile["data_provenance"] = "historical_pytest_fixture"
                connection.execute("UPDATE candidates SET raw_cv_json=?, anonymized_cv_json=? WHERE id=?",
                                   (json.dumps(raw), json.dumps(anon), cid))
            for jid, title in jobs:
                title += " [test fixture]"
                connection.execute("UPDATE job_requisitions SET title=? WHERE id=?", (title, jid))
                record = connection.execute("SELECT data FROM job_description_data WHERE job_id=?", (jid,)).fetchone()
                if record:
                    data = json.loads(record[0])
                    data["title"] = title
                    connection.execute("UPDATE job_description_data SET data=? WHERE job_id=?", (json.dumps(data), jid))
        print(f"Applied. Full database backup: {backup}")
    connection.close()


if __name__ == "__main__":
    main()

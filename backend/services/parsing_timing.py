"""Durable parsing averages from successful, uncached file timings."""
from datetime import datetime, timezone
from math import isfinite


def parsing_statistics(progress_records):
    durations = []
    for progress in progress_records:
        for item in (progress or {}).get("files", []):
            if item.get("status") != "COMPLETED" or item.get("duplicate_removed"):
                continue
            try:
                start = datetime.fromisoformat(item["started_at"])
                end = datetime.fromisoformat(item["finished_at"])
                start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
                end = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
                elapsed = (end - start).total_seconds() * 1000
            except (KeyError, TypeError, ValueError):
                continue
            if elapsed > 0 and isfinite(elapsed):
                durations.append(elapsed)
    average = sum(durations) / len(durations) if durations else None
    return {
        "sample_count": len(durations),
        "average_ms": average,
        "estimates": [{"cv_count": count, "duration_ms": average * count if average is not None else None}
                      for count in (1, 10, 25, 50, 100)],
    }

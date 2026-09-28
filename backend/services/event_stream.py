"""
backend/services/event_stream.py
Real-time Server-Sent Events (SSE) broadcaster for streaming batch screening progress,
per-candidate lifecycle events, and job pipeline updates.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Set, Union
from uuid import UUID

from backend.db.repository import DatabaseRepository

logger = logging.getLogger("recruitment_screening.event_stream")


class EventBroadcaster:
    """Manages real-time in-memory pub/sub queues for SSE subscriber clients."""

    def __init__(self) -> None:
        # Maps batch_id (str) -> Set[asyncio.Queue]
        self._batch_subscribers: Dict[str, Set[asyncio.Queue]] = {}
        # Maps job_id (str) -> Set[asyncio.Queue]
        self._job_subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def register_batch_subscriber(self, batch_id: str) -> asyncio.Queue:
        """Registers a new listener queue for the specified batch ID."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            if batch_id not in self._batch_subscribers:
                self._batch_subscribers[batch_id] = set()
            self._batch_subscribers[batch_id].add(queue)
        logger.debug(f"Registered subscriber for batch {batch_id}. Active: {len(self._batch_subscribers[batch_id])}")
        return queue

    async def unregister_batch_subscriber(self, batch_id: str, queue: asyncio.Queue) -> None:
        """Removes a listener queue when the client disconnects."""
        async with self._lock:
            if batch_id in self._batch_subscribers:
                self._batch_subscribers[batch_id].discard(queue)
                if not self._batch_subscribers[batch_id]:
                    del self._batch_subscribers[batch_id]
        logger.debug(f"Unregistered subscriber for batch {batch_id}")

    async def publish_batch_event(
        self,
        batch_id: Union[UUID, str],
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Broadcasts an event message to all active subscribers of the given batch ID."""
        bid_str = str(batch_id)
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with self._lock:
            subscribers = list(self._batch_subscribers.get(bid_str, []))

        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except Exception as e:
                logger.warning(f"Error putting event to subscriber queue for batch {bid_str}: {e}")

    async def subscribe_batch_events(
        self,
        batch_id: Union[UUID, str],
        heartbeat_interval: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator yielding SSE formatted chunks for a specific batch.
        Initializes with current state from DB, streams live events, and terminates on completion.
        """
        bid_str = str(batch_id)
        queue = await self.register_batch_subscriber(bid_str)

        try:
            # 1. Emit initial state from database
            record = await DatabaseRepository.get_batch_job(bid_str)
            if record:
                processed = record.processed_files + record.failed_files
                pct = round((processed / max(record.total_files, 1)) * 100.0, 1)
                init_data = {
                    "batch_id": bid_str,
                    "status": record.status,
                    "total_files": record.total_files,
                    "processed_files": record.processed_files,
                    "failed_files": record.failed_files,
                    "progress_percentage": min(pct, 100.0),
                    "results": record.results_json or [],
                }
                yield f"event: initial_state\ndata: {json.dumps(init_data)}\n\n"

                if record.status in ["COMPLETED", "FAILED", "PARTIAL"]:
                    yield f"event: complete\ndata: {json.dumps(init_data)}\n\n"
                    return

            # 2. Stream live events
            while True:
                try:
                    event_msg = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                    event_name = event_msg.get("event", "message")
                    event_data = event_msg.get("data", {})
                    yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"

                    # If batch is complete or failed, close the stream gracefully
                    if event_name in ["batch_completed", "batch_failed", "complete"]:
                        break

                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment to prevent proxy/client drop
                    yield ": ping\n\n"

        except (asyncio.CancelledError, GeneratorExit):
            logger.debug(f"Client disconnected from SSE stream for batch {bid_str}")
        finally:
            await self.unregister_batch_subscriber(bid_str, queue)


# Global singleton broadcaster instance
event_broadcaster = EventBroadcaster()

"""
tests/test_event_stream.py
Tests for Server-Sent Events (SSE) real-time streaming of batch screening progress.
"""

import asyncio
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from backend.db.repository import DatabaseRepository
from backend.main import app
from backend.services.event_stream import EventBroadcaster, event_broadcaster


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_event_broadcaster_pub_sub():
    """Verify EventBroadcaster delivers published events to subscriber queues."""
    broadcaster = EventBroadcaster()
    batch_id = str(uuid4())

    queue = await broadcaster.register_batch_subscriber(batch_id)
    assert queue.empty()

    test_data = {"filename": "candidate1.pdf", "progress": 50.0}
    await broadcaster.publish_batch_event(batch_id, "file_completed", test_data)

    assert not queue.empty()
    item = queue.get_nowait()
    assert item["event"] == "file_completed"
    assert item["data"] == test_data
    assert "timestamp" in item

    await broadcaster.unregister_batch_subscriber(batch_id, queue)
    assert batch_id not in broadcaster._batch_subscribers


@pytest.mark.asyncio
async def test_subscribe_batch_events_lifecycle():
    """Verify subscribe_batch_events emits initial_state and handles complete lifecycle."""
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(
        total_files=2,
        batch_id=batch_id,
    )

    gen = event_broadcaster.subscribe_batch_events(batch_id, heartbeat_interval=0.5)

    # 1. First yielded chunk must be initial_state
    first_chunk = await gen.__anext__()
    assert "event: initial_state" in first_chunk
    assert f'"batch_id": "{str(batch_id)}"' in first_chunk

    # 2. Publish an event in background
    async def publish_events():
        await asyncio.sleep(0.05)
        await event_broadcaster.publish_batch_event(
            batch_id=batch_id,
            event_type="file_completed",
            data={"filename": "test.pdf", "processed_count": 1},
        )
        await asyncio.sleep(0.05)
        await event_broadcaster.publish_batch_event(
            batch_id=batch_id,
            event_type="batch_completed",
            data={"batch_id": str(batch_id), "status": "COMPLETED"},
        )

    task = asyncio.create_task(publish_events())

    # 3. Next chunk should be file_completed
    second_chunk = await gen.__anext__()
    assert "event: file_completed" in second_chunk
    assert "test.pdf" in second_chunk

    # 4. Next chunk should be batch_completed and terminate stream
    third_chunk = await gen.__anext__()
    assert "event: batch_completed" in third_chunk

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    await task


def test_batch_stream_endpoint_not_found(client):
    """Verify GET /api/v1/cv/batch/{id}/stream returns 404 for nonexistent batch."""
    fake_id = uuid4()
    res = client.get(f"/api/v1/cv/batch/{fake_id}/stream")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_batch_stream_endpoint_initial_state(client):
    """Verify streaming response connects and outputs SSE formatted text."""
    batch_id = uuid4()
    await DatabaseRepository.create_batch_job(
        total_files=1,
        batch_id=batch_id,
    )
    await DatabaseRepository.update_batch_progress(
        batch_id=batch_id,
        candidate_result={"status": "COMPLETED", "filename": "test.pdf"},
        is_success=True,
        is_completed=True,
    )

    with client.stream("GET", f"/api/v1/cv/batch/{batch_id}/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        content = response.read().decode("utf-8")
        assert "event: initial_state" in content
        assert "event: complete" in content
        assert str(batch_id) in content


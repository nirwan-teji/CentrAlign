from __future__ import annotations

import pytest

from server.events import EventBroker


@pytest.mark.asyncio
async def test_event_broker_delivers_events():
    broker = EventBroker()
    stream = broker.subscribe("run-1")
    reader = stream.__aiter__()
    import asyncio
    pending = asyncio.create_task(reader.__anext__())
    await asyncio.sleep(0)
    await broker.publish("run-1", {"type": "status", "value": "running"})
    assert await pending == {"type": "status", "value": "running"}
    await stream.aclose()

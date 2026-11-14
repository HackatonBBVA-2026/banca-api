import asyncio
import json
import pytest

from src.broadcaster import Broadcaster, broadcaster


@pytest.mark.asyncio
async def test_subscriber_registration_and_count():
    b = Broadcaster()
    assert b.subscriber_count == 0

    q1 = await b.subscribe()
    assert isinstance(q1, asyncio.Queue)
    assert q1.maxsize == 100
    assert b.subscriber_count == 1

    q2 = await b.subscribe()
    assert b.subscriber_count == 2

    await b.unsubscribe(q1)
    assert b.subscriber_count == 1

    await b.unsubscribe(q2)
    assert b.subscriber_count == 0


@pytest.mark.asyncio
async def test_fanout_to_multiple_subscribers():
    b = Broadcaster()
    q1 = await b.subscribe()
    q2 = await b.subscribe()
    q3 = await b.subscribe()

    payload = {"id": 101, "monto": "-25.50", "categoria": "Alimentación"}
    notified = await b.broadcast("movimiento", payload)
    assert notified == 3

    expected_frame = f"event: movimiento\ndata: {json.dumps(payload, default=str)}\n\n"

    msg1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    msg2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    msg3 = await asyncio.wait_for(q3.get(), timeout=1.0)

    assert msg1 == expected_frame
    assert msg2 == expected_frame
    assert msg3 == expected_frame


@pytest.mark.asyncio
async def test_broadcast_with_string_data():
    b = Broadcaster()
    q = await b.subscribe()

    notified = await b.broadcast("ping", '{"status":"ok"}')
    assert notified == 1

    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg == 'event: ping\ndata: {"status":"ok"}\n\n'


@pytest.mark.asyncio
async def test_graceful_queue_overflow_handling():
    b = Broadcaster()
    q_full = await b.subscribe()
    q_normal = await b.subscribe()

    # Fill q_full up to maxsize (100)
    for i in range(100):
        q_full.put_nowait(f"dummy-{i}")
    assert q_full.full()

    # Broadcast should not raise asyncio.QueueFull, drops frame for q_full, delivers to q_normal
    notified = await b.broadcast("overflow_test", {"value": 999})
    assert notified == 1

    assert q_full.qsize() == 100
    msg_normal = await asyncio.wait_for(q_normal.get(), timeout=1.0)
    assert "overflow_test" in msg_normal


@pytest.mark.asyncio
async def test_unsubscribe_idempotency_and_isolation():
    b = Broadcaster()
    q1 = await b.subscribe()
    q2 = await b.subscribe()

    await b.unsubscribe(q1)
    # Repeating unsubscribe should not raise error
    await b.unsubscribe(q1)

    notified = await b.broadcast("test", {"msg": "hello"})
    assert notified == 1
    assert q1.empty()
    assert not q2.empty()


@pytest.mark.asyncio
async def test_broadcast_ping():
    b = Broadcaster()
    q = await b.subscribe()
    notified = await b.broadcast_ping()
    assert notified == 1
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg.startswith("event: ping\ndata: ")
    assert "alive" in msg


@pytest.mark.asyncio
async def test_global_broadcaster_instance():
    assert isinstance(broadcaster, Broadcaster)

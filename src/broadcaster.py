import asyncio
import json
from typing import Any, Dict, Set, Union


class Broadcaster:
    """In-memory Server-Sent Events (SSE) broadcaster with a multi-subscriber registry."""

    def __init__(self, queue_maxsize: int = 100):
        self._subscribers: Set[asyncio.Queue] = set()
        self._queue_maxsize = queue_maxsize

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def subscribe(self) -> asyncio.Queue:
        """Creates and registers a new subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
        self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Removes a subscriber queue from the registry safely."""
        self._subscribers.discard(queue)

    async def broadcast(self, event_name: str, data: Union[Dict[str, Any], str, Any]) -> int:
        """Formats SSE frame and fans out to all active subscriber queues via put_nowait().
        
        Safely drops frames if an individual subscriber queue is full without blocking other subscribers.
        Returns the count of subscribers successfully notified.
        """
        if hasattr(data, "model_dump"):
            json_str = json.dumps(data.model_dump(mode="json"), default=str)
        elif isinstance(data, (dict, list)):
            json_str = json.dumps(data, default=str)
        else:
            json_str = str(data)

        frame = f"event: {event_name}\ndata: {json_str}\n\n"

        notified = 0
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(frame)
                notified += 1
            except asyncio.QueueFull:
                # Drop frame safely when client buffer is congested
                pass

        return notified

    async def broadcast_ping(self) -> int:
        """Heartbeat ping frame broadcast to keep connections alive."""
        return await self.broadcast("ping", {"status": "alive"})

    def clear(self) -> None:
        """Clear all subscribers (useful for test teardown)."""
        self._subscribers.clear()


# Global broadcaster singleton
broadcaster = Broadcaster()

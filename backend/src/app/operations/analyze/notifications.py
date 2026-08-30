"""Best-effort transient notifications for analysis tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import TypeAlias

from app.operations.analyze.events import AnalysisEvent, AnalysisProgressEvent

logger = logging.getLogger(__name__)


class _CloseSignal:
    """Private marker used to close a purged session's active streams."""


_CLOSE = _CloseSignal()
_QueueItem: TypeAlias = AnalysisEvent | _CloseSignal
_SubscriberQueue: TypeAlias = asyncio.Queue[_QueueItem]


def _replace_queued(queue: _SubscriberQueue, item: _QueueItem) -> None:
    try:
        queued = queue.get_nowait()
    except asyncio.QueueEmpty:
        queued = None

    if queued is _CLOSE or (
        isinstance(item, AnalysisProgressEvent)
        and queued is not None
        and not isinstance(queued, AnalysisProgressEvent)
    ):
        item = queued

    queue.put_nowait(item)


class Subscription:
    """One eagerly registered, independently closeable SSE subscription."""

    __slots__ = ("_closed", "_queue", "session_id")

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._closed = False
        self._queue: _SubscriberQueue = asyncio.Queue(maxsize=1)

    def __aiter__(self) -> Subscription:
        return self

    async def __anext__(self) -> AnalysisEvent:
        if self._closed:
            raise StopAsyncIteration
        item = await self._queue.get()
        if isinstance(item, _CloseSignal):
            self.close()
            raise StopAsyncIteration
        return item

    def enqueue(self, event: AnalysisEvent) -> None:
        if not self._closed:
            _replace_queued(self._queue, event)

    def close(self) -> None:
        """Close and unregister this subscription exactly once."""
        if self._closed:
            return
        self._closed = True
        subscribers = _subscribers.get(self.session_id)
        if subscribers is not None:
            subscribers.discard(self)
            if not subscribers:
                _subscribers.pop(self.session_id, None)
        _replace_queued(self._queue, _CLOSE)


_subscribers: dict[str, set[Subscription]] = {}


def register(session_id: str) -> Subscription:
    """Eagerly register one session subscription before streaming begins."""
    subscription = Subscription(session_id)
    _subscribers.setdefault(session_id, set()).add(subscription)
    return subscription


async def publish(event: AnalysisEvent) -> None:
    """Publish an ephemeral event without changing durable analysis state."""
    for subscription in list(_subscribers.get(event.session_id, set())):
        try:
            subscription.enqueue(event)
        except Exception:
            logger.error(
                "Failed to publish analysis event session_id=%s event_type=%s",
                event.session_id,
                event.event_type,
            )


async def publish_progress(
    session_id: str,
    *,
    message: str,
    progress: float,
    page: int | None = None,
) -> None:
    """Publish one transient progress update."""
    await publish(
        AnalysisProgressEvent(
            session_id=session_id,
            page=page,
            progress=progress,
            message=message,
        )
    )


def discard_session(session_id: str) -> None:
    """Close active streams and discard state after permanent deletion."""
    for subscription in _subscribers.pop(session_id, set()):
        subscription.close()

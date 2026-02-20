from __future__ import annotations

import asyncio
import inspect
import json
import logging
import threading
from typing import Any, Callable, Iterator

from fastapi import Request
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)


def _serialize_exception(exc: Exception) -> dict[str, Any]:
    payload = {"error": str(exc)}
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        payload["status_code"] = status_code
    cause = getattr(exc, "cause", None)
    if isinstance(cause, dict):
        payload["cause"] = cause
    return payload


async def iter_sse(
    request: Request,
    iterator_factory: Callable[..., Iterator[dict[str, Any]]],
    *,
    typed_events: bool = False,
) -> Iterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    stop = threading.Event()
    url = getattr(request, "url", None)
    path = getattr(url, "path", "unknown")
    client = getattr(request, "client", None)
    client_host = getattr(client, "host", "unknown")
    logger.info("SSE stream opened path=%s client=%s", path, client_host)

    def build_iterator() -> Iterator[dict[str, Any]]:
        try:
            signature = inspect.signature(iterator_factory)
            if len(signature.parameters) > 0:
                return iterator_factory(stop)
        except (TypeError, ValueError):
            # Builtins/callables without introspectable signatures fall through.
            pass
        return iterator_factory()

    def worker() -> None:
        logger.debug("SSE worker thread started")
        try:
            for item in build_iterator():
                if stop.is_set():
                    logger.debug("SSE worker detected stop signal")
                    break
                item_type = item.get("type") if isinstance(item, dict) else None
                logger.debug("SSE worker queued payload type=%s", item_type)
                loop.call_soon_threadsafe(queue.put_nowait, ("data", item))
        except Exception as exc:
            logger.exception("SSE worker iterator raised an exception")
            loop.call_soon_threadsafe(queue.put_nowait, ("error", _serialize_exception(exc)))
        finally:
            logger.debug("SSE worker thread finished")
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE stream disconnected by client path=%s client=%s", path, client_host)
                break
            try:
                event, payload = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("SSE stream task cancelled path=%s client=%s", path, client_host)
                break

            if event == "data":
                encoded = jsonable_encoder(payload)
                if typed_events and isinstance(payload, dict):
                    event_name = payload.get("type")
                    if isinstance(event_name, str) and event_name:
                        yield f"event: {event_name}\ndata: {json.dumps(encoded)}\n\n"
                        continue
                yield f"data: {json.dumps(encoded)}\n\n"
                continue

            if event == "error":
                encoded = jsonable_encoder(payload)
                yield f"event: proxy_error\ndata: {json.dumps(encoded)}\n\n"
                break

            break
    finally:
        stop.set()
        logger.info("SSE stream closed path=%s client=%s", path, client_host)

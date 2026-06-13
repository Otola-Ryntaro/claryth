"""Request-size and resource-use guards for the local API."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from threading import Lock
from time import monotonic
from typing import Awaitable, Callable


ASGIApp = Callable[[dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]], Awaitable[None]]


class RequestBodyTooLarge(Exception):
    pass


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return

        total = 0
        response_started = False

        async def limited_receive() -> dict:
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message: dict) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(self, scope: dict, receive: Callable, send: Callable) -> None:
        body = json.dumps({"detail": "リクエストボディが大きすぎます。"}, ensure_ascii=False).encode(
            "utf-8"
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


@dataclass(frozen=True)
class GuardLease:
    expensive: bool


class RequestGuard:
    def __init__(
        self,
        max_concurrent: int,
        max_expensive: int,
        rate_limits: dict[str, int],
        window_seconds: float = 60.0,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_expensive = max_expensive
        self.rate_limits = rate_limits
        self.window_seconds = window_seconds
        self.expensive_paths = {"/v1/resolve", "/v1/ollama/warmup"}
        self._active = 0
        self._active_expensive = 0
        self._calls = {path: deque() for path in rate_limits}
        self._lock = Lock()

    def try_enter(self, path: str) -> tuple[GuardLease | None, int]:
        now = monotonic()
        expensive = path in self.expensive_paths
        with self._lock:
            if self._active >= self.max_concurrent:
                return None, 1
            if expensive and self._active_expensive >= self.max_expensive:
                return None, 1
            calls = self._calls.get(path)
            limit = self.rate_limits.get(path)
            if calls is not None and limit is not None:
                cutoff = now - self.window_seconds
                while calls and calls[0] <= cutoff:
                    calls.popleft()
                if len(calls) >= limit:
                    retry_after = max(1, int(self.window_seconds - (now - calls[0])) + 1)
                    return None, retry_after
                calls.append(now)
            self._active += 1
            if expensive:
                self._active_expensive += 1
        return GuardLease(expensive=expensive), 0

    def release(self, lease: GuardLease) -> None:
        with self._lock:
            self._active -= 1
            if lease.expensive:
                self._active_expensive -= 1

    def reset(self) -> None:
        with self._lock:
            self._active = 0
            self._active_expensive = 0
            for calls in self._calls.values():
                calls.clear()

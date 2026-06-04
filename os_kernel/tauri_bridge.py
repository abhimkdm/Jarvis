"""Optional event bridge to a Tauri + React shell (console-only when unbridged)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


EventListener = Callable[[str, dict], Awaitable[None] | None]


class TauriBridge:
    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def register_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    async def emit(self, event: str, payload: dict) -> None:
        print(f"[TauriBridge] {event}: {payload}")
        for listener in self._listeners:
            result = listener(event, payload)
            if asyncio.iscoroutine(result):
                await result

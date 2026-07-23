"""Lazy model registry and async prefetch."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.runtime.io_pool import IOPool
from app.runtime.resource_budget import ResourceBudget


Loader = Callable[[], Any]


@dataclass(frozen=True)
class ModelSpec:
    name: str
    estimated_mb: int
    loader: Loader
    idle_ttl_sec: int = 180


@dataclass
class LoadedModel:
    spec: ModelSpec
    value: Any
    loaded_at: float
    last_used: float


class ModelRegistry:
    """Registers lazy model loaders and prefetches likely hot models."""

    def __init__(self, budget: ResourceBudget, io_pool: IOPool) -> None:
        self.budget = budget
        self.io_pool = io_pool
        self.specs: dict[str, ModelSpec] = {}
        self.loaded: dict[str, LoadedModel] = {}
        self.loading: dict[str, asyncio.Task[Any]] = {}

    def register(self, spec: ModelSpec) -> None:
        self.specs[spec.name] = spec

    async def get(self, name: str) -> Any | None:
        if name in self.loaded:
            self.loaded[name].last_used = time.monotonic()
            return self.loaded[name].value

        spec = self.specs.get(name)
        if spec is None:
            return None
        if not self.budget.can_load(spec.estimated_mb):
            return None

        task = self.loading.get(name)
        if task is None:
            task = asyncio.create_task(self.io_pool.run(spec.loader))
            self.loading[name] = task

        value = await task
        self.loading.pop(name, None)
        now = time.monotonic()
        self.loaded[name] = LoadedModel(spec=spec, value=value, loaded_at=now, last_used=now)
        return value

    def prefetch(self, names: list[str]) -> None:
        for name in names:
            if name in self.loaded or name in self.loading:
                continue
            spec = self.specs.get(name)
            if spec is None or not self.budget.can_load(spec.estimated_mb):
                continue
            self.loading[name] = asyncio.create_task(self.io_pool.run(spec.loader))

    def unload_idle(self) -> list[str]:
        now = time.monotonic()
        unloaded: list[str] = []
        for name, loaded in list(self.loaded.items()):
            if now - loaded.last_used >= loaded.spec.idle_ttl_sec:
                self.loaded.pop(name, None)
                unloaded.append(name)
        return unloaded

    async def shutdown(self) -> None:
        for task in self.loading.values():
            task.cancel()
        if self.loading:
            await asyncio.gather(*self.loading.values(), return_exceptions=True)
        self.loading.clear()
        self.loaded.clear()


def placeholder_loader(name: str) -> Loader:
    """Create a cheap placeholder loader until real OCR/YOLO/LLM imports land."""

    def load() -> dict[str, Any]:
        return {
            "name": name,
            "status": "placeholder-loaded",
            "loaded_at": time.time(),
        }

    return load


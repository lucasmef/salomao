from __future__ import annotations

from collections import defaultdict

import pytest

from app.services import analytics_hybrid


class _FakeRedisLiveCache:
    def __init__(self) -> None:
        self.items: dict[str, str] = {}
        self.indexes: dict[str, set[str]] = defaultdict(set)

    def get(self, key: str) -> str | None:
        return self.items.get(key)

    def set(self, key: str, value: str, ttl_seconds: int, index_key: str) -> None:  # noqa: ARG002
        self.items[key] = value
        self.indexes[index_key].add(key)

    def clear_company(self, prefix: str, company_id: str, kinds=None) -> None:
        target_kinds = tuple(kinds or analytics_hybrid.DEFAULT_ANALYTICS_KINDS)
        for kind in target_kinds:
            index_key = f"{prefix}:index:{company_id}:{kind}"
            for key in self.indexes.pop(index_key, set()):
                self.items.pop(key, None)


@pytest.fixture(autouse=True)
def _fake_redis_cache_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _FakeRedisLiveCache()
    analytics_hybrid.reset_live_cache_backend_for_tests()
    monkeypatch.setattr(analytics_hybrid, "_get_live_cache_backend", lambda: backend)

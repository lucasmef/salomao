from __future__ import annotations

from collections.abc import Iterable


OPEN_STATUS = "open"
LEGACY_OPEN_STATUS = "planned"
PARTIAL_STATUS = "partial"
SETTLED_STATUS = "settled"
CANCELLED_STATUS = "cancelled"

OPEN_STATUS_QUERY_VALUES = (OPEN_STATUS, LEGACY_OPEN_STATUS)
OPEN_FILTER_QUERY_VALUES = (OPEN_STATUS, LEGACY_OPEN_STATUS, PARTIAL_STATUS)
UNSETTLED_STATUS_QUERY_VALUES = (OPEN_STATUS, LEGACY_OPEN_STATUS, PARTIAL_STATUS)


def normalize_open_alias(value: str | None, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    if normalized == LEGACY_OPEN_STATUS:
        return OPEN_STATUS
    return normalized


def is_open_like_status(value: str | None) -> bool:
    return normalize_open_alias(value) == OPEN_STATUS


def expand_status_filter_values(statuses: Iterable[str] | None) -> list[str]:
    if not statuses:
        return []
    effective: set[str] = set()
    for raw_status in statuses:
        normalized = normalize_open_alias(raw_status)
        if not normalized:
            continue
        if normalized == OPEN_STATUS:
            effective.update(OPEN_FILTER_QUERY_VALUES)
            continue
        effective.add(normalized)
    return list(effective)

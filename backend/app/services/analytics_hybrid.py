from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.finance import FinancialEntry
from app.db.models.linx import LinxMovement, SalesSnapshot
from app.db.models.reporting import AnalyticsMonthlySnapshot, AnalyticsSnapshotRebuildTask
from app.db.models.security import Company

HISTORICAL_CUTOFF = date(2026, 1, 1)
ANALYTICS_REPORTS_OVERVIEW = "reports_overview"
ANALYTICS_CASHFLOW_OVERVIEW = "cashflow_overview"
ANALYTICS_DASHBOARD_OVERVIEW = "dashboard_overview"
ANALYTICS_REVENUE_COMPARISON = "revenue_comparison"
DEFAULT_ANALYTICS_KINDS = (
    ANALYTICS_REPORTS_OVERVIEW,
    ANALYTICS_CASHFLOW_OVERVIEW,
    ANALYTICS_DASHBOARD_OVERVIEW,
)
DEFAULT_LIVE_INDEX_TTL_SECONDS = 86400


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def month_end(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1) - timedelta(days=1)
    return date(value.year, value.month + 1, 1) - timedelta(days=1)


def is_full_month_period(start: date, end: date) -> bool:
    return start == month_start(start) and end == month_end(start)


def is_historical_period(start: date, end: date) -> bool:
    return end < HISTORICAL_CUTOFF


def is_live_period(start: date, end: date) -> bool:
    return start >= HISTORICAL_CUTOFF


def iter_month_segments(start: date, end: date) -> list[tuple[date, date]]:
    segments: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        current_month_end = month_end(cursor)
        segment_end = min(current_month_end, end)
        segments.append((cursor, segment_end))
        cursor = segment_end + timedelta(days=1)
    return segments


def params_key_for(params: dict[str, object] | None) -> str:
    if not params:
        return ""
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def snapshot_params_for_cashflow(
    *,
    account_id: str | None,
    include_purchase_planning: bool,
    include_crediario_receivables: bool,
) -> dict[str, object]:
    return {
        "account_id": account_id or "",
        "include_purchase_planning": include_purchase_planning,
        "include_crediario_receivables": include_crediario_receivables,
    }


class _RedisLiveCache:
    def __init__(self, redis_client: Redis, prefix: str) -> None:
        self._redis = redis_client
        self._prefix = prefix

    def get(self, key: str) -> str | None:
        return self._redis.get(key)

    def set(self, key: str, value: str, ttl_seconds: int, index_key: str) -> None:
        pipeline = self._redis.pipeline()
        pipeline.setex(key, ttl_seconds, value)
        pipeline.sadd(index_key, key)
        pipeline.expire(index_key, max(ttl_seconds, DEFAULT_LIVE_INDEX_TTL_SECONDS))
        pipeline.execute()

    def clear_company(self, prefix: str, company_id: str, kinds: Iterable[str] | None = None) -> None:
        target_kinds = tuple(kinds or DEFAULT_ANALYTICS_KINDS)
        for kind in target_kinds:
            index_key = f"{prefix}:index:{company_id}:{kind}"
            keys = list(self._redis.smembers(index_key))
            if keys:
                self._redis.delete(*keys)
            self._redis.delete(index_key)


_live_cache_backend_lock = Lock()
_live_cache_backend: _RedisLiveCache | None = None


def _get_live_cache_backend() -> _RedisLiveCache:
    global _live_cache_backend
    with _live_cache_backend_lock:
        if _live_cache_backend is not None:
            return _live_cache_backend
        settings = get_settings()
        try:
            client = Redis.from_url(settings.analytics_redis_url, decode_responses=True)
            client.ping()
            _live_cache_backend = _RedisLiveCache(client, settings.analytics_redis_prefix)
            return _live_cache_backend
        except RedisError as error:  # pragma: no cover - configuration/runtime guard
            raise RuntimeError(f"Redis indisponivel para analytics: {error}") from error


def reset_live_cache_backend_for_tests() -> None:
    global _live_cache_backend
    with _live_cache_backend_lock:
        _live_cache_backend = None


def _live_cache_prefix() -> str:
    return get_settings().analytics_redis_prefix


def _live_cache_key(
    *,
    kind: str,
    company_id: str,
    start: date,
    end: date,
    params_key: str,
) -> str:
    return f"{_live_cache_prefix()}:payload:{company_id}:{kind}:{start.isoformat()}:{end.isoformat()}:{params_key or 'default'}"


def _live_cache_index_key(*, kind: str, company_id: str) -> str:
    return f"{_live_cache_prefix()}:index:{company_id}:{kind}"


def read_live_cache(model_cls, *, kind: str, company_id: str, start: date, end: date, params: dict[str, object] | None = None):
    key = _live_cache_key(
        kind=kind,
        company_id=company_id,
        start=start,
        end=end,
        params_key=params_key_for(params),
    )
    cached = _get_live_cache_backend().get(key)
    if not cached:
        return None
    return model_cls.model_validate_json(cached)


def write_live_cache(
    payload,
    *,
    kind: str,
    company_id: str,
    start: date,
    end: date,
    ttl_seconds: int,
    params: dict[str, object] | None = None,
) -> None:
    key = _live_cache_key(
        kind=kind,
        company_id=company_id,
        start=start,
        end=end,
        params_key=params_key_for(params),
    )
    _get_live_cache_backend().set(
        key,
        payload.model_dump_json(),
        ttl_seconds,
        _live_cache_index_key(kind=kind, company_id=company_id),
    )


def read_live_json_cache(
    *,
    kind: str,
    company_id: str,
    start: date,
    end: date,
    params: dict[str, object] | None = None,
) -> dict[str, object] | list[object] | None:
    key = _live_cache_key(
        kind=kind,
        company_id=company_id,
        start=start,
        end=end,
        params_key=params_key_for(params),
    )
    cached = _get_live_cache_backend().get(key)
    if not cached:
        return None
    return json.loads(cached)


def write_live_json_cache(
    payload: dict[str, object] | list[object],
    *,
    kind: str,
    company_id: str,
    start: date,
    end: date,
    ttl_seconds: int,
    params: dict[str, object] | None = None,
) -> None:
    key = _live_cache_key(
        kind=kind,
        company_id=company_id,
        start=start,
        end=end,
        params_key=params_key_for(params),
    )
    _get_live_cache_backend().set(
        key,
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        ttl_seconds,
        _live_cache_index_key(kind=kind, company_id=company_id),
    )


def clear_live_cache(company_id: str | None = None, *, kinds: Iterable[str] | None = None) -> None:
    if company_id is None:
        reset_live_cache_backend_for_tests()
        return
    _get_live_cache_backend().clear_company(_live_cache_prefix(), company_id, kinds)


def read_monthly_snapshot(
    db: Session,
    model_cls,
    *,
    company_id: str,
    kind: str,
    snapshot_month: date,
    params: dict[str, object] | None = None,
):
    record = db.scalar(
        select(AnalyticsMonthlySnapshot).where(
            AnalyticsMonthlySnapshot.company_id == company_id,
            AnalyticsMonthlySnapshot.analytics_kind == kind,
            AnalyticsMonthlySnapshot.snapshot_month == snapshot_month,
            AnalyticsMonthlySnapshot.params_key == params_key_for(params),
        )
    )
    if record is None:
        return None
    return model_cls.model_validate(record.payload_json)


def upsert_monthly_snapshot(
    db: Session,
    payload,
    *,
    company_id: str,
    kind: str,
    snapshot_month: date,
    params: dict[str, object] | None = None,
) -> None:
    params_key = params_key_for(params)
    record = db.scalar(
        select(AnalyticsMonthlySnapshot).where(
            AnalyticsMonthlySnapshot.company_id == company_id,
            AnalyticsMonthlySnapshot.analytics_kind == kind,
            AnalyticsMonthlySnapshot.snapshot_month == snapshot_month,
            AnalyticsMonthlySnapshot.params_key == params_key,
        )
    )
    if record is None:
        record = AnalyticsMonthlySnapshot(
            company_id=company_id,
            analytics_kind=kind,
            snapshot_month=snapshot_month,
            params_key=params_key,
        )
        db.add(record)
    record.params_json = params or None
    record.payload_json = payload.model_dump(mode="json")
    db.flush()


def enqueue_snapshot_rebuild(
    db: Session,
    *,
    company_id: str,
    kind: str,
    snapshot_month: date,
    params: dict[str, object] | None = None,
    reason: str | None = None,
) -> None:
    params_key = params_key_for(params)
    task = db.scalar(
        select(AnalyticsSnapshotRebuildTask).where(
            AnalyticsSnapshotRebuildTask.company_id == company_id,
            AnalyticsSnapshotRebuildTask.analytics_kind == kind,
            AnalyticsSnapshotRebuildTask.snapshot_month == snapshot_month,
            AnalyticsSnapshotRebuildTask.params_key == params_key,
        )
    )
    if task is None:
        task = AnalyticsSnapshotRebuildTask(
            company_id=company_id,
            analytics_kind=kind,
            snapshot_month=snapshot_month,
            params_key=params_key,
        )
        db.add(task)
    task.params_json = params or None
    task.reason = reason
    task.status = "pending"
    task.last_error = None
    db.flush()


def _mark_rebuild_completed(task: AnalyticsSnapshotRebuildTask) -> None:
    task.status = "completed"
    task.attempts += 1
    task.last_error = None


def _mark_rebuild_failed(task: AnalyticsSnapshotRebuildTask, error: Exception) -> None:
    task.status = "failed"
    task.attempts += 1
    task.last_error = str(error)


def read_snapshot_or_rebuild(
    db: Session,
    model_cls,
    *,
    company: Company,
    kind: str,
    snapshot_month: date,
    build_func,
    params: dict[str, object] | None = None,
):
    params_key = params_key_for(params)
    task = db.scalar(
        select(AnalyticsSnapshotRebuildTask).where(
            AnalyticsSnapshotRebuildTask.company_id == company.id,
            AnalyticsSnapshotRebuildTask.analytics_kind == kind,
            AnalyticsSnapshotRebuildTask.snapshot_month == snapshot_month,
            AnalyticsSnapshotRebuildTask.params_key == params_key,
        )
    )
    if task is None or task.status != "pending":
        cached = read_monthly_snapshot(
            db,
            model_cls,
            company_id=company.id,
            kind=kind,
            snapshot_month=snapshot_month,
            params=params,
        )
        if cached is not None:
            return cached
    payload = build_func()
    upsert_monthly_snapshot(
        db,
        payload,
        company_id=company.id,
        kind=kind,
        snapshot_month=snapshot_month,
        params=params,
    )
    if task is not None:
        _mark_rebuild_completed(task)
        db.flush()
    return payload


def _extract_historical_months_from_dates(affected_dates: Iterable[date]) -> list[date]:
    months = sorted({month_start(value) for value in affected_dates if value < HISTORICAL_CUTOFF})
    return months


def _append_date_if_missing(values: list[date], candidate: date | None) -> None:
    if candidate is not None:
        values.append(candidate)


def infer_company_historical_months(db: Session, company_id: str) -> list[date]:
    candidates: list[date] = []
    entry_row = db.execute(
        select(
            func.min(FinancialEntry.issue_date),
            func.min(FinancialEntry.competence_date),
            func.min(FinancialEntry.due_date),
            func.max(FinancialEntry.issue_date),
            func.max(FinancialEntry.competence_date),
            func.max(FinancialEntry.due_date),
        ).where(
            FinancialEntry.company_id == company_id,
            FinancialEntry.is_deleted.is_(False),
        )
    ).one()
    movement_row = db.execute(
        select(
            func.min(LinxMovement.launch_date),
            func.min(LinxMovement.issue_date),
            func.max(LinxMovement.launch_date),
            func.max(LinxMovement.issue_date),
        ).where(LinxMovement.company_id == company_id)
    ).one()
    snapshot_row = db.execute(
        select(
            func.min(SalesSnapshot.snapshot_date),
            func.max(SalesSnapshot.snapshot_date),
        ).where(SalesSnapshot.company_id == company_id)
    ).one()
    for item in entry_row:
        _append_date_if_missing(candidates, item if isinstance(item, date) else None)
    for item in movement_row:
        if isinstance(item, datetime):
            _append_date_if_missing(candidates, item.date())
    for item in snapshot_row:
        _append_date_if_missing(candidates, item if isinstance(item, date) else None)
    historical_candidates = [value for value in candidates if value < HISTORICAL_CUTOFF]
    if not historical_candidates:
        return []
    start_month = month_start(min(historical_candidates))
    end_month = month_start(max(historical_candidates))
    months: list[date] = []
    cursor = start_month
    while cursor <= end_month and cursor < HISTORICAL_CUTOFF:
        months.append(cursor)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def queue_historical_rebuilds(
    db: Session,
    *,
    company_id: str,
    affected_dates: Iterable[date] | None = None,
    kinds: Iterable[str] = DEFAULT_ANALYTICS_KINDS,
    reason: str | None = None,
) -> list[date]:
    months = (
        _extract_historical_months_from_dates(affected_dates)
        if affected_dates is not None
        else infer_company_historical_months(db, company_id)
    )
    for snapshot_month in months:
        for kind in kinds:
            enqueue_snapshot_rebuild(
                db,
                company_id=company_id,
                kind=kind,
                snapshot_month=snapshot_month,
                reason=reason,
            )
    return months


def process_snapshot_rebuild_queue(db: Session, company: Company, *, limit: int = 12) -> list[tuple[str, date]]:
    tasks = list(
        db.scalars(
            select(AnalyticsSnapshotRebuildTask)
            .where(
                AnalyticsSnapshotRebuildTask.company_id == company.id,
                AnalyticsSnapshotRebuildTask.status == "pending",
            )
            .order_by(
                AnalyticsSnapshotRebuildTask.snapshot_month.asc(),
                AnalyticsSnapshotRebuildTask.analytics_kind.asc(),
            )
            .limit(limit)
        )
    )
    rebuilt: list[tuple[str, date]] = []
    for task in tasks:
        try:
            segment_start = task.snapshot_month
            segment_end = month_end(task.snapshot_month)
            if task.analytics_kind == ANALYTICS_REPORTS_OVERVIEW:
                from app.services.reports import build_reports_overview

                payload = build_reports_overview(db, company, start=segment_start, end=segment_end)
            elif task.analytics_kind == ANALYTICS_CASHFLOW_OVERVIEW:
                from app.services.cashflow import build_cashflow_overview

                params = task.params_json or {}
                payload = build_cashflow_overview(
                    db,
                    company,
                    start_date=segment_start,
                    end_date=segment_end,
                    account_id=params.get("account_id") or None,
                    include_purchase_planning=bool(params.get("include_purchase_planning", True)),
                    include_crediario_receivables=bool(params.get("include_crediario_receivables", True)),
                )
            elif task.analytics_kind == ANALYTICS_DASHBOARD_OVERVIEW:
                from app.services.dashboard import build_dashboard_overview

                payload = build_dashboard_overview(db, company, start=segment_start, end=segment_end)
            else:
                raise ValueError(f"Analytics kind nao suportado: {task.analytics_kind}")
            upsert_monthly_snapshot(
                db,
                payload,
                company_id=company.id,
                kind=task.analytics_kind,
                snapshot_month=task.snapshot_month,
                params=task.params_json,
            )
            _mark_rebuild_completed(task)
            rebuilt.append((task.analytics_kind, task.snapshot_month))
        except Exception as error:  # pragma: no cover - defensive
            _mark_rebuild_failed(task, error)
        db.flush()
    return rebuilt


def invalidate_live_analytics(company_id: str | None, *, include_sales_history: bool = False) -> None:
    if company_id is None:
        clear_live_cache(None)
        return
    kinds = list(DEFAULT_ANALYTICS_KINDS)
    if include_sales_history:
        kinds.append(ANALYTICS_REVENUE_COMPARISON)
    clear_live_cache(company_id, kinds=kinds)

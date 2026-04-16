"""
linx_sales_snapshot.py

Rebuilds SalesSnapshot records from the LinxMovement mirror table,
eliminating the need for manual XLS uploads to keep the revenue
comparison chart up to date.

Strategy:
  - Group LinxMovement rows with movement_type='sale' by launch_date
    to compute gross_revenue per day.
  - Subtract sale_return amounts from the same day to get net gross_revenue.
  - Upsert into sales_snapshots (delete-then-insert for affected days).

Note: Fields such as card_revenue, pix_revenue, cash_revenue, etc. are not
available in the movements API and will be left at zero. Only gross_revenue
is populated by this service. The DRE already uses linx_movements directly,
so both the chart and DRE will now agree.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.db.models.imports import ImportBatch
from app.db.models.linx import LinxMovement, SalesSnapshot
from app.db.models.security import Company
from app.schemas.imports import ImportResult

LINX_SALES_SNAPSHOT_SOURCE = "linx_movements_snapshot"


def _affected_dates_from_batch(db: Session, *, company_id: str, batch_id: str) -> set[date]:
    """Return all distinct launch_date.date() values touched by a given import batch."""
    rows = db.execute(
        select(func.date(LinxMovement.launch_date))
        .where(
            LinxMovement.company_id == company_id,
            LinxMovement.last_seen_batch_id == batch_id,
            LinxMovement.launch_date.is_not(None),
        )
        .distinct()
    ).scalars()
    return {r for r in rows if r is not None}


def _query_daily_revenue(
    db: Session,
    *,
    company_id: str,
    start_date: date,
    end_date: date,
) -> dict[date, Decimal]:
    """
    Aggregate gross revenue per calendar day from LinxMovement.
    gross_revenue = SUM(sale total_amount) - SUM(sale_return total_amount)
    """
    rows = db.execute(
        select(
            func.date(LinxMovement.launch_date).label("day"),
            func.coalesce(
                func.sum(
                    case(
                        (LinxMovement.movement_type == "sale", func.coalesce(LinxMovement.total_amount, 0)),
                        else_=0,
                    )
                ),
                0,
            ).label("sales"),
            func.coalesce(
                func.sum(
                    case(
                        (LinxMovement.movement_type == "sale_return", func.coalesce(LinxMovement.total_amount, 0)),
                        else_=0,
                    )
                ),
                0,
            ).label("returns"),
        )
        .where(
            LinxMovement.company_id == company_id,
            LinxMovement.movement_group == "sale",
            LinxMovement.canceled.is_(False),
            LinxMovement.excluded.is_(False),
            LinxMovement.launch_date >= func.cast(start_date.isoformat(), LinxMovement.launch_date.type),
            LinxMovement.launch_date < func.cast(
                date(end_date.year, end_date.month, calendar.monthrange(end_date.year, end_date.month)[1] + 1
                     if end_date.month < 12 else 1,
                     ).isoformat() if end_date.month < 12 else
                date(end_date.year + 1, 1, 1).isoformat(),
                LinxMovement.launch_date.type,
            ),
        )
        .group_by(func.date(LinxMovement.launch_date))
    ).all()

    result: dict[date, Decimal] = {}
    for row in rows:
        day = row[0]
        if day is None:
            continue
        if isinstance(day, str):
            day = date.fromisoformat(day)
        gross = Decimal(str(row[1])) - Decimal(str(row[2]))
        result[day] = max(gross, Decimal("0.00"))
    return result


def _query_daily_revenue_for_dates(
    db: Session,
    *,
    company_id: str,
    target_dates: set[date],
) -> dict[date, Decimal]:
    """Aggregate gross revenue for a specific set of dates."""
    if not target_dates:
        return {}

    rows = db.execute(
        select(
            func.date(LinxMovement.launch_date).label("day"),
            func.coalesce(
                func.sum(
                    case(
                        (LinxMovement.movement_type == "sale", func.coalesce(LinxMovement.total_amount, 0)),
                        else_=0,
                    )
                ),
                0,
            ).label("sales"),
            func.coalesce(
                func.sum(
                    case(
                        (LinxMovement.movement_type == "sale_return", func.coalesce(LinxMovement.total_amount, 0)),
                        else_=0,
                    )
                ),
                0,
            ).label("returns"),
        )
        .where(
            LinxMovement.company_id == company_id,
            LinxMovement.movement_group == "sale",
            LinxMovement.canceled.is_(False),
            LinxMovement.excluded.is_(False),
            func.date(LinxMovement.launch_date).in_(list(target_dates)),
        )
        .group_by(func.date(LinxMovement.launch_date))
    ).all()

    result: dict[date, Decimal] = {}
    for row in rows:
        day = row[0]
        if day is None:
            continue
        if isinstance(day, str):
            day = date.fromisoformat(day)
        gross = Decimal(str(row[1])) - Decimal(str(row[2]))
        result[day] = max(gross, Decimal("0.00"))
    return result


def rebuild_sales_snapshots_from_movements(
    db: Session,
    company: Company,
    *,
    affected_dates: set[date] | None = None,
) -> ImportResult:
    """
    Upsert SalesSnapshot records derived from LinxMovement rows.

    Args:
        db: SQLAlchemy session.
        company: Company whose data to rebuild.
        affected_dates: If provided, only rebuild snapshots for these
            specific dates. If None, perform a full rebuild from all
            movement data (expensive, for initial load only).

    Returns:
        ImportResult with a description of what was done.
    """
    if affected_dates is not None:
        dates_to_rebuild = affected_dates
    else:
        # Full rebuild: collect all days that have movement data
        all_days_rows = db.execute(
            select(func.date(LinxMovement.launch_date))
            .where(
                LinxMovement.company_id == company.id,
                LinxMovement.movement_group == "sale",
                LinxMovement.launch_date.is_not(None),
            )
            .distinct()
        ).scalars()
        dates_to_rebuild = {r for r in all_days_rows if r is not None}
        # Also keep any existing snapshot dates so they get recalculated
        existing_days_rows = db.execute(
            select(SalesSnapshot.snapshot_date).where(SalesSnapshot.company_id == company.id)
        ).scalars()
        dates_to_rebuild.update(existing_days_rows)

    if not dates_to_rebuild:
        return ImportResult(
            batch=_create_snapshot_batch(db, company.id, inserted=0, updated=0, deleted=0),
            message="Nenhum dado de movimentos encontrado para gerar snapshots.",
        )

    # Query revenue for all affected dates at once
    revenue_by_date = _query_daily_revenue_for_dates(
        db,
        company_id=company.id,
        target_dates=dates_to_rebuild,
    )

    # Load existing snapshots for affected dates
    existing_snapshots: dict[date, SalesSnapshot] = {}
    for snap in db.scalars(
        select(SalesSnapshot).where(
            SalesSnapshot.company_id == company.id,
            SalesSnapshot.snapshot_date.in_(list(dates_to_rebuild)),
        )
    ):
        existing_snapshots[snap.snapshot_date] = snap

    inserted = 0
    updated = 0
    deleted = 0

    for day in sorted(dates_to_rebuild):
        gross_revenue = revenue_by_date.get(day, Decimal("0.00"))
        existing = existing_snapshots.get(day)

        if gross_revenue == Decimal("0.00") and existing is not None:
            # No movement data for this day but snapshot exists — delete it
            db.delete(existing)
            deleted += 1
            continue

        if gross_revenue == Decimal("0.00"):
            # No data and no snapshot — skip
            continue

        if existing is None:
            snap = SalesSnapshot(
                company_id=company.id,
                snapshot_date=day,
                gross_revenue=gross_revenue,
                cash_revenue=Decimal("0.00"),
                check_sight_revenue=Decimal("0.00"),
                check_term_revenue=Decimal("0.00"),
                inhouse_credit_revenue=Decimal("0.00"),
                card_revenue=Decimal("0.00"),
                convenio_revenue=Decimal("0.00"),
                pix_revenue=Decimal("0.00"),
                financing_revenue=Decimal("0.00"),
            )
            db.add(snap)
            inserted += 1
        else:
            existing.gross_revenue = gross_revenue
            # Preserve other revenue fields (card, pix, etc.) if already set
            # from manual XLS imports — only override gross_revenue
            updated += 1

    batch = _create_snapshot_batch(db, company.id, inserted=inserted, updated=updated, deleted=deleted)
    db.flush()

    parts = []
    if inserted:
        parts.append(f"{inserted} snapshot(s) criado(s)")
    if updated:
        parts.append(f"{updated} atualizado(s)")
    if deleted:
        parts.append(f"{deleted} removido(s) (sem movimentos)")
    if not parts:
        message = "SalesSnapshot ja esta sincronizado com os movimentos."
    else:
        message = "SalesSnapshot atualizado a partir dos movimentos Linx. " + ", ".join(parts) + "."

    return ImportResult(batch=batch, message=message)


def _create_snapshot_batch(
    db: Session,
    company_id: str,
    *,
    inserted: int,
    updated: int,
    deleted: int,
) -> ImportBatch:
    batch = ImportBatch(
        company_id=company_id,
        source_type=LINX_SALES_SNAPSHOT_SOURCE,
        filename="linx-sales-snapshot-rebuild",
        fingerprint=None,
        status="processed",
        records_total=inserted + updated + deleted,
        records_valid=inserted + updated,
        records_invalid=deleted,
    )
    db.add(batch)
    db.flush()
    return batch

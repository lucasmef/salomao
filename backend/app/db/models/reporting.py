from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, IdMixin, TimestampMixin


class ReportLayout(Base, IdMixin, TimestampMixin):
    __tablename__ = "report_layouts"
    __table_args__ = (UniqueConstraint("company_id", "kind", name="uq_report_layout_company_kind"),)

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")

    lines = relationship(
        "ReportLayoutLine",
        back_populates="layout",
        cascade="all, delete-orphan",
        order_by="ReportLayoutLine.position",
    )


class ReportLayoutLine(Base, IdMixin, TimestampMixin):
    __tablename__ = "report_layout_lines"

    layout_id: Mapped[str] = mapped_column(ForeignKey("report_layouts.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(160))
    line_type: Mapped[str] = mapped_column(String(20), default="source")
    operation: Mapped[str] = mapped_column(String(10), default="add")
    special_source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    summary_binding: Mapped[str | None] = mapped_column(String(60), nullable=True)
    show_on_dashboard: Mapped[bool] = mapped_column(Boolean, default=False)
    show_percent: Mapped[bool] = mapped_column(Boolean, default=True)
    percent_mode: Mapped[str] = mapped_column(String(30), default="reference_line")
    percent_reference_line_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)

    layout = relationship("ReportLayout", back_populates="lines")
    group_assignments = relationship(
        "ReportLayoutLineGroup",
        back_populates="line",
        cascade="all, delete-orphan",
        order_by="ReportLayoutLineGroup.position",
    )
    formula_items = relationship(
        "ReportLayoutFormulaItem",
        back_populates="line",
        cascade="all, delete-orphan",
        foreign_keys="ReportLayoutFormulaItem.line_id",
        order_by="ReportLayoutFormulaItem.position",
    )


class ReportLayoutLineGroup(Base, IdMixin, TimestampMixin):
    __tablename__ = "report_layout_line_groups"

    line_id: Mapped[str] = mapped_column(ForeignKey("report_layout_lines.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    group_name: Mapped[str] = mapped_column(String(120))

    line = relationship("ReportLayoutLine", back_populates="group_assignments")


class ReportLayoutFormulaItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "report_layout_formula_items"

    line_id: Mapped[str] = mapped_column(ForeignKey("report_layout_lines.id"), index=True)
    referenced_line_id: Mapped[str] = mapped_column(ForeignKey("report_layout_lines.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    operation: Mapped[str] = mapped_column(String(10), default="add")

    line = relationship("ReportLayoutLine", back_populates="formula_items", foreign_keys=[line_id])
    referenced_line = relationship("ReportLayoutLine", foreign_keys=[referenced_line_id])


class AnalyticsMonthlySnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "analytics_monthly_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "analytics_kind",
            "snapshot_month",
            "params_key",
            name="uq_analytics_month_snapshot_scope",
        ),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    analytics_kind: Mapped[str] = mapped_column(String(40), index=True)
    snapshot_month: Mapped[object] = mapped_column(Date, index=True)
    params_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    params_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON)


class AnalyticsSnapshotRebuildTask(Base, IdMixin, TimestampMixin):
    __tablename__ = "analytics_snapshot_rebuild_tasks"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "analytics_kind",
            "snapshot_month",
            "params_key",
            name="uq_analytics_snapshot_rebuild_scope",
        ),
    )

    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    analytics_kind: Mapped[str] = mapped_column(String(40), index=True)
    snapshot_month: Mapped[object] = mapped_column(Date, index=True)
    params_key: Mapped[str] = mapped_column(String(64), default="", index=True)
    params_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

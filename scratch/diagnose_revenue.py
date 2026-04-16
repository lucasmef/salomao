
from sqlalchemy import select, func
from app.db.base_class import SessionLocal
from app.db.models.finance import Account
from app.db.models.linx import SalesSnapshot
from app.db.models.security import Company
from decimal import Decimal
from datetime import date

def diagnose_revenue():
    db = SessionLocal()
    try:
        # 1. Total snapshots in 2026
        rows = db.execute(
            select(
                func.count(SalesSnapshot.id),
                func.sum(SalesSnapshot.gross_revenue),
                func.min(SalesSnapshot.snapshot_date),
                func.max(SalesSnapshot.snapshot_date)
            ).where(
                SalesSnapshot.snapshot_date >= date(2026, 1, 1),
                SalesSnapshot.snapshot_date <= date(2026, 12, 31)
            )
        ).one()
        print(f"2026 Stats: Count={rows[0]}, Sum={rows[1]}, Min={rows[2]}, Max={rows[3]}")

        # 2. April 2026 breakdown
        april_rows = db.execute(
            select(
                SalesSnapshot.snapshot_date,
                SalesSnapshot.gross_revenue,
                SalesSnapshot.company_id
            ).where(
                SalesSnapshot.snapshot_date >= date(2026, 4, 1),
                SalesSnapshot.snapshot_date <= date(2026, 4, 30)
            ).order_by(SalesSnapshot.snapshot_date)
        ).all()
        print("\nApril 2026 Breakdown:")
        for r in april_rows:
            print(f"Date: {r[0]}, Rev: {r[1]}, Co: {r[2]}")

        # 3. Check for multiple companies
        companies = db.execute(select(Company.id, Company.trade_name)).all()
        print("\nCompanies:")
        for c in companies:
            print(f"ID: {c[0]}, Name: {c[1]}")

    finally:
        db.close()

if __name__ == "__main__":
    diagnose_revenue()

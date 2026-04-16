import os
import sys

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.session import SessionLocal
from app.db.models.security import Company
from app.services.linx_sales_snapshot import rebuild_sales_snapshots_from_movements
from app.services.cache_invalidation import clear_dashboard_revenue_comparison_cache

def main():
    db = SessionLocal()
    try:
        companies = db.query(Company).all()
        for company in companies:
            print(f"Rebuilding for {company.trade_name}...")
            result = rebuild_sales_snapshots_from_movements(db, company, affected_dates=None)
            clear_dashboard_revenue_comparison_cache(company_id=company.id)
            print(f"Result: {result.message}")
        db.commit()
        print("Done!")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()

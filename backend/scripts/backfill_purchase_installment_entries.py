from __future__ import annotations

from app.db.session import SessionLocal
from app.services.purchase_planning import (
    ensure_purchase_installment_financial_entries,
    reconcile_purchase_invoice_links,
)


def main() -> None:
    with SessionLocal() as db:
        relinked_count = reconcile_purchase_invoice_links(db)
        repaired_count = ensure_purchase_installment_financial_entries(db)
        db.commit()
    print(f"Notas religadas: {relinked_count}")
    print(f"Parcelas reparadas: {repaired_count}")


if __name__ == "__main__":
    main()

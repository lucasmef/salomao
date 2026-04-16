import sys
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.db.models.finance import Account

engine = create_engine("postgresql://postgres:postgres@localhost:5432/salomao_dev")

with Session(engine) as session:
    accounts = session.scalars(select(Account)).all()
    print(f"Total accounts found: {len(accounts)}")
    for acc in accounts:
        print(f"ID: {acc.id} | Name: {acc.name} | Active: {acc.is_active} | Exclude: {acc.exclude_from_balance} | Type: {acc.account_type} | OFX: {acc.import_ofx_enabled}")

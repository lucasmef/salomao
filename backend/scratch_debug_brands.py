import os
import sys

# Set DATABASE_URL if needed
os.environ['DATABASE_URL'] = 'sqlite:///gestor_financeiro.db'

# Ensure we are in the right directory or add it to path
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()

print("--- Unique Brand Names containing 'veste' (case-insensitive) ---")
sql = text("SELECT DISTINCT brand_name FROM linx_products WHERE brand_name LIKE '%veste%' OR brand_name LIKE '%VESTE%'")
results = db.execute(sql).all()
for r in results:
    print(f"'{r[0]}'")

print("\n--- Unique Brand Names starting with 'V' ---")
sql = text("SELECT DISTINCT brand_name FROM linx_products WHERE brand_name LIKE 'v%' OR brand_name LIKE 'V%'")
results = db.execute(sql).all()
for r in results:
    print(f"'{r[0]}'")

print("\n--- Normalization Test ---")
from app.services.import_parsers import normalize_label
for r in results:
    name = r[0]
    if name:
        print(f"Name: '{name}' -> Normalized: '{normalize_label(name)}'")

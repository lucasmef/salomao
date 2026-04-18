import os
import sys

# Set DATABASE_URL if needed
os.environ['DATABASE_URL'] = 'sqlite:///gestor_financeiro.db'

# Ensure we are in the right directory or add it to path
sys.path.append(os.getcwd())

from sqlalchemy import create_engine, inspect
from app.db.session import engine

inspector = inspect(engine)
tables = inspector.get_table_names()
print("Tables in database:")
for table in tables:
    print(f"- {table}")

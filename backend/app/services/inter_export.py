import io
import os
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.boleto import BoletoRecord
from app.db.models.export_jobs import BoletoExportJob
from app.db.models.security import Company
from app.services.inter import InterApiClient, _resolve_pdf_download_account

SETTINGS = get_settings()
EXPORT_DIR = Path(SETTINGS.root_dir or ".") / ".runtime" / "exports"


def ensure_export_dir():
    if not EXPORT_DIR.exists():
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def create_export_job(db: Session, company: Company, boleto_ids: list[str]) -> BoletoExportJob:
    job = BoletoExportJob(
        company_id=company.id,
        status="pending",
        total_count=len(boleto_ids),
        processed_count=0,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_export_job(session_factory, job_id: str, company_id: str, boleto_ids: list[str]):
    ensure_export_dir()
    
    db = session_factory()
    job = db.get(BoletoExportJob, job_id)
    if not job:
        db.close()
        return

    try:
        job.status = "processing"
        db.commit()

        # Load boletos and group by client
        stmt = (
            select(BoletoRecord)
            .where(BoletoRecord.id.in_(boleto_ids))
            .where(BoletoRecord.company_id == company_id)
            .order_by(BoletoRecord.due_date.asc())
        )
        records = list(db.scalars(stmt).all())
        
        if not records:
            raise ValueError("Nenhum boleto encontrado para exportacao.")

        by_client = defaultdict(list)
        for r in records:
            # Group by client_key if available, fallback to client_name
            key = r.client_key or r.client_name or "Cliente Desconhecido"
            by_client[key].append(r)

        client_count = len(by_client)
        temp_dir = EXPORT_DIR / f"job_{job_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        merged_files = []
        
        # We'll use one client instance per account to optimize token usage
        clients_cache = {}

        def get_inter_client(record):
            nonlocal db
            company = db.get(Company, company_id)
            account, config = _resolve_pdf_download_account(db, company, record)
            if account.id not in clients_cache:
                clients_cache[account.id] = InterApiClient(config)
            return clients_cache[account.id]

        processed = 0
        for client_key, client_records in by_client.items():
            merger = PdfWriter()
            client_name_sanitized = "".join(c if c.isalnum() else "_" for c in client_records[0].client_name or client_key)
            
            for record in client_records:
                try:
                    client = get_inter_client(record)
                    pdf_bytes = client.get_charge_pdf(str(record.inter_codigo_solicitacao))
                    merger.append(io.BytesIO(pdf_bytes))
                except Exception as e:
                    print(f"Erro ao baixar PDF para boleto {record.id}: {e}")
                    # We continue with other boletos
                
                processed += 1
                job.processed_count = processed
                db.commit()

            if len(merger.pages) > 0:
                merged_filename = f"{client_name_sanitized}.pdf"
                merged_path = temp_dir / merged_filename
                with open(merged_path, "wb") as f:
                    merger.write(f)
                merged_files.append(merged_path)
            
            merger.close()

        # Finalize
        for c in clients_cache.values():
            c.close()

        if not merged_files:
            raise ValueError("Nenhum PDF foi baixado com sucesso.")

        final_filename = ""
        if client_count == 1:
            # Single client -> Single PDF
            final_filename = merged_files[0].name
            final_path = EXPORT_DIR / f"{job_id}_{final_filename}"
            shutil.move(str(merged_files[0]), str(final_path))
        else:
            # Multiple clients -> ZIP
            final_filename = f"boletos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            final_path = EXPORT_DIR / f"{job_id}_{final_filename}"
            with zipfile.ZipFile(final_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
                for f in merged_files:
                    zipf.write(f, arcname=f.name)

        shutil.rmtree(temp_dir)
        
        job.status = "completed"
        job.file_path = str(final_path)
        job.filename = final_filename
        db.commit()

    except Exception as e:
        db.rollback()
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
    finally:
        db.close()


def cleanup_old_exports():
    if not EXPORT_DIR.exists():
        return
    
    now = datetime.now(timezone.utc)
    for f in EXPORT_DIR.glob("*"):
        if f.is_file():
            # Check if it matches our pattern {job_id}_{filename}
            # Or if it's an old directory
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if now - mtime > timedelta(hours=24):
                try:
                    if f.is_dir():
                        shutil.rmtree(f)
                    else:
                        f.unlink()
                except Exception:
                    pass

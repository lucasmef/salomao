from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _table_names(connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
    }


def _columns(connection, table_name: str) -> set[str]:
    return {
        row[1]
        for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
    }


def _add_column_if_missing(connection, table_name: str, column_name: str, sql_type: str) -> None:
    if table_name not in _table_names(connection):
        return
    if column_name in _columns(connection, table_name):
        return
    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))


def _create_index_if_missing(connection, table_name: str, index_name: str, create_sql: str) -> None:
    if table_name not in _table_names(connection):
        return
    existing_indexes = {
        row[0]
        for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))
    }
    if index_name in existing_indexes:
        return
    connection.execute(text(create_sql))


def _create_table_if_missing(connection, table_name: str, create_sql: str) -> None:
    if table_name in _table_names(connection):
        return
    connection.execute(text(create_sql))


def _normalize_collection_name(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.lower().strip()
    return (
        lowered.replace("ã", "a")
        .replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )


def _infer_collection_structure(row) -> tuple[int | None, str | None, str]:
    name = _normalize_collection_name(row["name"])
    start_date = row["start_date"] or ""
    end_date = row["end_date"] or ""
    season_year = None
    for raw_date in [start_date, end_date]:
        if raw_date and len(str(raw_date)) >= 4 and str(raw_date)[:4].isdigit():
            season_year = int(str(raw_date)[:4])
            break

    season_type = None
    if "inverno" in name:
        season_type = "winter"
    elif "verao" in name:
        season_type = "summer"

    season_phase = "high" if "alto" in name else "main"
    return season_year, season_type, season_phase


def _season_label(season_type: str | None, season_year: int | None) -> str | None:
    if not season_type or not season_year:
        return None
    labels = {
        "summer": "Verao",
        "winter": "Inverno",
    }
    base_label = labels.get(season_type)
    if not base_label:
        return None
    return f"{base_label} {season_year}"


def _consolidate_collection_seasons(connection) -> None:
    if "collection_seasons" not in _table_names(connection):
        return

    rows = list(
        connection.execute(
            text(
                """
                SELECT id, company_id, name, season_year, season_type, start_date, end_date, notes, is_active
                FROM collection_seasons
                ORDER BY company_id, start_date, end_date, created_at, name
                """
            )
        ).mappings()
    )
    if not rows:
        return

    grouped: dict[tuple[str, int, str], list[dict[str, object]]] = {}
    for raw_row in rows:
        row = dict(raw_row)
        season_year = row["season_year"]
        season_type = row["season_type"]
        season_phase = "main"
        if not season_year or not season_type:
            inferred_year, inferred_type, inferred_phase = _infer_collection_structure(row)
            season_year = season_year or inferred_year
            season_type = season_type or inferred_type
            season_phase = inferred_phase
            connection.execute(
                text(
                    """
                    UPDATE collection_seasons
                    SET season_year = :season_year,
                        season_type = :season_type
                    WHERE id = :collection_id
                    """
                ),
                {
                    "collection_id": row["id"],
                    "season_year": season_year,
                    "season_type": season_type,
                },
            )
        else:
            _, _, season_phase = _infer_collection_structure(row)
        row["season_year"] = season_year
        row["season_type"] = season_type
        row["season_phase"] = season_phase
        if season_year and season_type:
            grouped.setdefault((str(row["company_id"]), int(season_year), str(season_type)), []).append(row)

    tables_with_phase = [
        ("purchase_plans", "collection_id"),
        ("purchase_invoices", "collection_id"),
        ("purchase_deliveries", "collection_id"),
        ("financial_entries", "collection_id"),
    ]

    for company_id, season_year, season_type in grouped:
        key_rows = grouped[(company_id, season_year, season_type)]
        canonical = next((row for row in key_rows if row["season_phase"] == "main"), key_rows[0])
        season_label = _season_label(season_type, season_year) or str(canonical["name"] or "")

        start_dates = [str(row["start_date"]) for row in key_rows if row["start_date"]]
        end_dates = [str(row["end_date"]) for row in key_rows if row["end_date"]]
        canonical_start = min(start_dates) if start_dates else canonical["start_date"]
        canonical_end = max(end_dates) if end_dates else canonical["end_date"]
        is_active = 1 if any(bool(row["is_active"]) for row in key_rows) else 0

        connection.execute(
            text(
                """
                UPDATE collection_seasons
                SET name = :name,
                    season_year = :season_year,
                    season_type = :season_type,
                    start_date = :start_date,
                    end_date = :end_date,
                    is_active = :is_active
                WHERE id = :collection_id
                """
            ),
            {
                "collection_id": canonical["id"],
                "name": season_label,
                "season_year": season_year,
                "season_type": season_type,
                "start_date": canonical_start,
                "end_date": canonical_end,
                "is_active": is_active,
            },
        )

        for row in key_rows:
            season_phase = str(row["season_phase"] or "main")
            for table_name, collection_column in tables_with_phase:
                if table_name not in _table_names(connection):
                    continue
                connection.execute(
                    text(
                        f"""
                        UPDATE {table_name}
                        SET collection_id = :canonical_id,
                            season_phase = CASE
                                WHEN :season_phase = 'high' THEN 'high'
                                WHEN season_phase IS NULL OR season_phase = '' THEN 'main'
                                ELSE season_phase
                            END
                        WHERE {collection_column} = :source_id
                        """
                    ),
                    {
                        "canonical_id": canonical["id"],
                        "source_id": row["id"],
                        "season_phase": season_phase,
                    },
                )
            if row["id"] != canonical["id"]:
                connection.execute(
                    text("DELETE FROM collection_seasons WHERE id = :collection_id"),
                    {"collection_id": row["id"]},
                )


def ensure_schema_updates(engine: Engine) -> None:
    with engine.begin() as connection:
        _create_table_if_missing(
            connection,
            "purchase_brands",
            """
            CREATE TABLE purchase_brands (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                company_id VARCHAR(36) NOT NULL,
                name VARCHAR(140) NOT NULL,
                default_payment_term VARCHAR(120),
                notes TEXT,
                is_active BOOLEAN DEFAULT 1
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "purchase_brand_suppliers",
            """
            CREATE TABLE purchase_brand_suppliers (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                company_id VARCHAR(36) NOT NULL,
                brand_id VARCHAR(36) NOT NULL,
                supplier_id VARCHAR(36) NOT NULL
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "purchase_plan_suppliers",
            """
            CREATE TABLE purchase_plan_suppliers (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                company_id VARCHAR(36) NOT NULL,
                plan_id VARCHAR(36) NOT NULL,
                supplier_id VARCHAR(36) NOT NULL
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "report_layouts",
            """
            CREATE TABLE report_layouts (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                company_id VARCHAR(36) NOT NULL,
                kind VARCHAR(10) NOT NULL,
                name VARCHAR(120) DEFAULT '',
                FOREIGN KEY(company_id) REFERENCES companies(id)
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "report_layout_lines",
            """
            CREATE TABLE report_layout_lines (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                layout_id VARCHAR(36) NOT NULL,
                position INTEGER DEFAULT 0,
                name VARCHAR(160) NOT NULL,
                line_type VARCHAR(20) DEFAULT 'source',
                operation VARCHAR(10) DEFAULT 'add',
                special_source VARCHAR(60),
                summary_binding VARCHAR(60),
                show_on_dashboard BOOLEAN DEFAULT 0,
                show_percent BOOLEAN DEFAULT 1,
                percent_mode VARCHAR(30) DEFAULT 'reference_line',
                percent_reference_line_id VARCHAR(36),
                is_active BOOLEAN DEFAULT 1,
                is_hidden BOOLEAN DEFAULT 0,
                FOREIGN KEY(layout_id) REFERENCES report_layouts(id)
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "report_layout_line_groups",
            """
            CREATE TABLE report_layout_line_groups (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                line_id VARCHAR(36) NOT NULL,
                position INTEGER DEFAULT 0,
                group_name VARCHAR(120) NOT NULL,
                FOREIGN KEY(line_id) REFERENCES report_layout_lines(id)
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "report_layout_formula_items",
            """
            CREATE TABLE report_layout_formula_items (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                line_id VARCHAR(36) NOT NULL,
                referenced_line_id VARCHAR(36) NOT NULL,
                position INTEGER DEFAULT 0,
                operation VARCHAR(10) DEFAULT 'add',
                FOREIGN KEY(line_id) REFERENCES report_layout_lines(id),
                FOREIGN KEY(referenced_line_id) REFERENCES report_layout_lines(id)
            )
            """,
        )

        account_columns = {
            "import_ofx_enabled": "BOOLEAN DEFAULT 0",
            "exclude_from_balance": "BOOLEAN DEFAULT 0",
            "inter_api_enabled": "BOOLEAN DEFAULT 0",
            "inter_environment": "VARCHAR(20) DEFAULT 'production'",
            "inter_api_base_url": "VARCHAR(255)",
            "inter_api_key": "VARCHAR(160)",
            "inter_account_number": "VARCHAR(30)",
            "inter_client_secret_encrypted": "TEXT",
            "inter_certificate_pem_encrypted": "TEXT",
            "inter_private_key_pem_encrypted": "TEXT",
        }
        for column_name, sql_type in account_columns.items():
            _add_column_if_missing(connection, "accounts", column_name, sql_type)
        _add_column_if_missing(connection, "purchase_brands", "default_payment_term", "VARCHAR(120)")
        _add_column_if_missing(connection, "report_layout_lines", "show_on_dashboard", "BOOLEAN DEFAULT 0")
        _add_column_if_missing(connection, "report_layout_lines", "show_percent", "BOOLEAN DEFAULT 1")
        _add_column_if_missing(connection, "report_layout_lines", "percent_mode", "VARCHAR(30) DEFAULT 'reference_line'")
        _add_column_if_missing(connection, "report_layout_lines", "percent_reference_line_id", "VARCHAR(36)")
        if "accounts" in _table_names(connection) and "import_ofx_enabled" in _columns(connection, "accounts"):
            connection.execute(
                text(
                    "UPDATE accounts "
                    "SET import_ofx_enabled = 1 "
                    "WHERE (account_type IN ('checking', 'savings') OR bank_code IS NOT NULL) "
                    "AND COALESCE(import_ofx_enabled, 0) = 0"
                )
            )

        _add_column_if_missing(connection, "categories", "report_subgroup", "VARCHAR(120)")
        _add_column_if_missing(connection, "financial_entries", "brand_id", "VARCHAR(36)")
        _add_column_if_missing(connection, "financial_entries", "season_phase", "VARCHAR(20) DEFAULT 'main'")
        _add_column_if_missing(connection, "purchase_plans", "brand_id", "VARCHAR(36)")
        _add_column_if_missing(connection, "purchase_plans", "season_phase", "VARCHAR(20) DEFAULT 'main'")
        _add_column_if_missing(connection, "purchase_invoices", "brand_id", "VARCHAR(36)")
        _add_column_if_missing(connection, "purchase_invoices", "season_phase", "VARCHAR(20) DEFAULT 'main'")
        _add_column_if_missing(connection, "purchase_deliveries", "brand_id", "VARCHAR(36)")
        _add_column_if_missing(connection, "purchase_deliveries", "season_phase", "VARCHAR(20) DEFAULT 'main'")
        _add_column_if_missing(connection, "collection_seasons", "season_year", "INTEGER")
        _add_column_if_missing(connection, "collection_seasons", "season_type", "VARCHAR(20)")
        company_columns = {
            "linx_base_url": "VARCHAR(255)",
            "linx_username": "VARCHAR(160)",
            "linx_password_encrypted": "VARCHAR(512)",
            "linx_sales_view_name": "VARCHAR(160)",
            "linx_receivables_view_name": "VARCHAR(160)",
            "linx_payables_view_name": "VARCHAR(160)",
            "linx_auto_sync_enabled": "BOOLEAN DEFAULT 0",
            "linx_auto_sync_alert_email": "VARCHAR(255)",
            "linx_auto_sync_last_run_at": "DATETIME",
            "linx_birthday_alert_last_sent_at": "DATETIME",
            "linx_auto_sync_last_status": "VARCHAR(20)",
            "linx_auto_sync_last_error": "TEXT",
        }
        for column_name, sql_type in company_columns.items():
            _add_column_if_missing(connection, "companies", column_name, sql_type)

        _add_column_if_missing(connection, "linx_customers", "birth_date", "DATE")

        user_columns = {
            "mfa_enabled": "BOOLEAN DEFAULT 0",
            "mfa_secret_encrypted": "VARCHAR(512)",
            "mfa_pending_secret_encrypted": "VARCHAR(512)",
            "mfa_enrolled_at": "DATETIME",
        }
        for column_name, sql_type in user_columns.items():
            _add_column_if_missing(connection, "users", column_name, sql_type)

        auth_session_columns = {
            "last_seen_at": "DATETIME",
            "is_active": "BOOLEAN DEFAULT 1",
        }
        for column_name, sql_type in auth_session_columns.items():
            _add_column_if_missing(connection, "auth_sessions", column_name, sql_type)

        _create_table_if_missing(
            connection,
            "mfa_trusted_devices",
            """
            CREATE TABLE mfa_trusted_devices (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_id VARCHAR(36) NOT NULL,
                token_hash VARCHAR(120) NOT NULL,
                expires_at DATETIME NOT NULL,
                last_seen_at DATETIME,
                is_active BOOLEAN DEFAULT 1,
                user_agent VARCHAR(512),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """,
        )
        _create_table_if_missing(
            connection,
            "purchase_payable_titles",
            """
            CREATE TABLE purchase_payable_titles (
                id VARCHAR(36) PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                company_id VARCHAR(36) NOT NULL,
                source_batch_id VARCHAR(36),
                last_seen_batch_id VARCHAR(36),
                source_reference VARCHAR(120) NOT NULL,
                issue_date DATE,
                due_date DATE,
                payable_code VARCHAR(40),
                company_code VARCHAR(20),
                installment_label VARCHAR(20),
                installment_number INTEGER,
                installments_total INTEGER,
                original_amount NUMERIC(14,2) DEFAULT 0,
                amount_with_charges NUMERIC(14,2),
                supplier_name VARCHAR(200) NOT NULL,
                supplier_code VARCHAR(20),
                document_number VARCHAR(80),
                document_series VARCHAR(20),
                status VARCHAR(30) DEFAULT 'open',
                purchase_invoice_id VARCHAR(36),
                purchase_installment_id VARCHAR(36),
                financial_entry_id VARCHAR(36),
                FOREIGN KEY(company_id) REFERENCES companies(id),
                FOREIGN KEY(source_batch_id) REFERENCES import_batches(id),
                FOREIGN KEY(last_seen_batch_id) REFERENCES import_batches(id),
                FOREIGN KEY(purchase_invoice_id) REFERENCES purchase_invoices(id),
                FOREIGN KEY(purchase_installment_id) REFERENCES purchase_installments(id),
                FOREIGN KEY(financial_entry_id) REFERENCES financial_entries(id)
            )
            """,
        )

        entry_columns = {
            "notes": "TEXT",
            "document_number": "VARCHAR(80)",
            "competence_date": "DATE",
            "discount_amount": "NUMERIC(14,2) DEFAULT 0",
            "penalty_amount": "NUMERIC(14,2) DEFAULT 0",
            "paid_amount": "NUMERIC(14,2) DEFAULT 0",
            "source_system": "VARCHAR(50)",
            "is_deleted": "BOOLEAN DEFAULT 0",
            "transfer_id": "VARCHAR(36)",
            "loan_installment_id": "VARCHAR(36)",
            "supplier_id": "VARCHAR(36)",
            "collection_id": "VARCHAR(36)",
            "purchase_invoice_id": "VARCHAR(36)",
            "purchase_installment_id": "VARCHAR(36)",
        }
        for column_name, sql_type in entry_columns.items():
            _add_column_if_missing(connection, "financial_entries", column_name, sql_type)

        recurrence_columns = {
            "title_template": "VARCHAR(160)",
            "counterparty_name": "VARCHAR(180)",
            "document_number": "VARCHAR(80)",
            "notes": "TEXT",
            "principal_amount": "NUMERIC(14,2) DEFAULT 0",
            "interest_amount": "NUMERIC(14,2) DEFAULT 0",
            "discount_amount": "NUMERIC(14,2) DEFAULT 0",
            "penalty_amount": "NUMERIC(14,2) DEFAULT 0",
            "interest_category_id": "VARCHAR(36)",
        }
        for column_name, sql_type in recurrence_columns.items():
            _add_column_if_missing(connection, "recurrence_rules", column_name, sql_type)

        boleto_customer_columns = {
            "include_interest": "BOOLEAN DEFAULT 0",
            "address_street": "VARCHAR(200)",
            "address_number": "VARCHAR(40)",
            "address_complement": "VARCHAR(160)",
            "neighborhood": "VARCHAR(120)",
            "city": "VARCHAR(120)",
            "state": "VARCHAR(10)",
            "zip_code": "VARCHAR(20)",
            "tax_id": "VARCHAR(20)",
            "state_registration": "VARCHAR(40)",
            "phone_primary": "VARCHAR(40)",
            "phone_secondary": "VARCHAR(40)",
            "mobile": "VARCHAR(40)",
        }
        for column_name, sql_type in boleto_customer_columns.items():
            _add_column_if_missing(connection, "boleto_customer_configs", column_name, sql_type)

        boleto_record_columns = {
            "inter_account_id": "VARCHAR(36)",
            "inter_codigo_solicitacao": "VARCHAR(80)",
            "inter_seu_numero": "VARCHAR(80)",
            "inter_nosso_numero": "VARCHAR(80)",
            "linha_digitavel": "VARCHAR(255)",
            "pix_copia_e_cola": "TEXT",
            "inter_txid": "VARCHAR(120)",
        }
        for column_name, sql_type in boleto_record_columns.items():
            _add_column_if_missing(connection, "boleto_records", column_name, sql_type)

        indexes = {
            "idx_financial_entries_company_status_due": ("financial_entries", (
                "CREATE INDEX idx_financial_entries_company_status_due "
                "ON financial_entries(company_id, status, due_date)"
            )),
            "idx_financial_entries_company_account_type": ("financial_entries", (
                "CREATE INDEX idx_financial_entries_company_account_type "
                "ON financial_entries(company_id, account_id, entry_type)"
            )),
            "idx_financial_entries_company_source": ("financial_entries", (
                "CREATE INDEX idx_financial_entries_company_source "
                "ON financial_entries(company_id, source_system)"
            )),
            "idx_financial_entries_company_dates": ("financial_entries", (
                "CREATE INDEX idx_financial_entries_company_dates "
                "ON financial_entries(company_id, competence_date, due_date)"
            )),
            "idx_financial_entries_company_supplier": ("financial_entries", (
                "CREATE INDEX idx_financial_entries_company_supplier "
                "ON financial_entries(company_id, supplier_id)"
            )),
            "idx_financial_entries_company_collection": ("financial_entries", (
                "CREATE INDEX idx_financial_entries_company_collection "
                "ON financial_entries(company_id, collection_id)"
            )),
            "idx_bank_transactions_company_posted_account": ("bank_transactions", (
                "CREATE INDEX idx_bank_transactions_company_posted_account "
                "ON bank_transactions(company_id, posted_at, account_id)"
            )),
            "idx_reconciliation_lines_transaction": ("reconciliation_lines", (
                "CREATE INDEX idx_reconciliation_lines_transaction "
                "ON reconciliation_lines(bank_transaction_id)"
            )),
            "idx_reconciliation_lines_entry": ("reconciliation_lines", (
                "CREATE INDEX idx_reconciliation_lines_entry "
                "ON reconciliation_lines(financial_entry_id)"
            )),
            "idx_purchase_plans_company_supplier_collection": ("purchase_plans", (
                "CREATE INDEX idx_purchase_plans_company_supplier_collection "
                "ON purchase_plans(company_id, supplier_id, collection_id)"
            )),
            "idx_purchase_plans_company_brand": ("purchase_plans", (
                "CREATE INDEX idx_purchase_plans_company_brand "
                "ON purchase_plans(company_id, brand_id)"
            )),
            "idx_purchase_invoices_company_supplier_issue": ("purchase_invoices", (
                "CREATE INDEX idx_purchase_invoices_company_supplier_issue "
                "ON purchase_invoices(company_id, supplier_id, issue_date)"
            )),
            "idx_purchase_invoices_company_brand_issue": ("purchase_invoices", (
                "CREATE INDEX idx_purchase_invoices_company_brand_issue "
                "ON purchase_invoices(company_id, brand_id, issue_date)"
            )),
            "idx_purchase_installments_company_due": ("purchase_installments", (
                "CREATE INDEX idx_purchase_installments_company_due "
                "ON purchase_installments(company_id, due_date, status)"
            )),
            "idx_purchase_payable_titles_company_source_ref": ("purchase_payable_titles", (
                "CREATE INDEX idx_purchase_payable_titles_company_source_ref "
                "ON purchase_payable_titles(company_id, source_reference)"
            )),
            "idx_purchase_payable_titles_company_due": ("purchase_payable_titles", (
                "CREATE INDEX idx_purchase_payable_titles_company_due "
                "ON purchase_payable_titles(company_id, due_date, status)"
            )),
            "idx_purchase_deliveries_company_supplier_collection": ("purchase_deliveries", (
                "CREATE INDEX idx_purchase_deliveries_company_supplier_collection "
                "ON purchase_deliveries(company_id, supplier_id, collection_id)"
            )),
            "idx_purchase_deliveries_company_brand_collection": ("purchase_deliveries", (
                "CREATE INDEX idx_purchase_deliveries_company_brand_collection "
                "ON purchase_deliveries(company_id, brand_id, collection_id)"
            )),
            "idx_purchase_brands_company_name": ("purchase_brands", (
                "CREATE INDEX idx_purchase_brands_company_name "
                "ON purchase_brands(company_id, name)"
            )),
            "idx_purchase_brand_suppliers_brand_supplier": ("purchase_brand_suppliers", (
                "CREATE INDEX idx_purchase_brand_suppliers_brand_supplier "
                "ON purchase_brand_suppliers(company_id, brand_id, supplier_id)"
            )),
            "idx_purchase_plan_suppliers_plan_supplier": ("purchase_plan_suppliers", (
                "CREATE INDEX idx_purchase_plan_suppliers_plan_supplier "
                "ON purchase_plan_suppliers(company_id, plan_id, supplier_id)"
            )),
            "idx_collection_seasons_company_year_type": ("collection_seasons", (
                "CREATE INDEX idx_collection_seasons_company_year_type "
                "ON collection_seasons(company_id, season_year, season_type)"
            )),
            "idx_mfa_trusted_devices_user_active": ("mfa_trusted_devices", (
                "CREATE INDEX idx_mfa_trusted_devices_user_active "
                "ON mfa_trusted_devices(user_id, is_active, expires_at)"
            )),
            "idx_mfa_trusted_devices_token_hash": ("mfa_trusted_devices", (
                "CREATE UNIQUE INDEX idx_mfa_trusted_devices_token_hash "
                "ON mfa_trusted_devices(token_hash)"
            )),
            "idx_report_layouts_company_kind": ("report_layouts", (
                "CREATE UNIQUE INDEX idx_report_layouts_company_kind "
                "ON report_layouts(company_id, kind)"
            )),
            "idx_report_layout_lines_layout_position": ("report_layout_lines", (
                "CREATE INDEX idx_report_layout_lines_layout_position "
                "ON report_layout_lines(layout_id, position)"
            )),
            "idx_report_layout_line_groups_line_position": ("report_layout_line_groups", (
                "CREATE INDEX idx_report_layout_line_groups_line_position "
                "ON report_layout_line_groups(line_id, position)"
            )),
            "idx_report_layout_formula_items_line_position": ("report_layout_formula_items", (
                "CREATE INDEX idx_report_layout_formula_items_line_position "
                "ON report_layout_formula_items(line_id, position)"
            )),
            "idx_linx_customers_birth_date": ("linx_customers", (
                "CREATE INDEX idx_linx_customers_birth_date "
                "ON linx_customers(birth_date)"
            )),
        }
        for index_name, (table_name, create_sql) in indexes.items():
            _create_index_if_missing(connection, table_name, index_name, create_sql)

        if "collection_seasons" in _table_names(connection):
            _consolidate_collection_seasons(connection)

        if {"purchase_plans", "purchase_plan_suppliers"}.issubset(_table_names(connection)):
            legacy_links = connection.execute(
                text(
                    """
                    SELECT company_id, id AS plan_id, supplier_id
                    FROM purchase_plans
                    WHERE supplier_id IS NOT NULL
                    """
                )
            ).mappings()
            for row in legacy_links:
                exists = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM purchase_plan_suppliers
                        WHERE company_id = :company_id
                          AND plan_id = :plan_id
                          AND supplier_id = :supplier_id
                        LIMIT 1
                        """
                    ),
                    dict(row),
                ).first()
                if exists:
                    continue
                connection.execute(
                    text(
                        """
                        INSERT INTO purchase_plan_suppliers (
                            id,
                            company_id,
                            plan_id,
                            supplier_id
                        ) VALUES (
                            :id,
                            :company_id,
                            :plan_id,
                            :supplier_id
                        )
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "company_id": row["company_id"],
                        "plan_id": row["plan_id"],
                        "supplier_id": row["supplier_id"],
                    },
                )

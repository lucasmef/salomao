from fastapi import APIRouter, Request, Response, status

from app.core.config import get_settings
from app.schemas.meta import ClientErrorLogCreate, DataSource, InstanceInfo, ModuleCard, ProjectOverview
from app.services.error_logging import log_client_issue

router = APIRouter()


@router.get("/instance", response_model=InstanceInfo)
def get_instance() -> InstanceInfo:
    settings = get_settings()
    database_backend = "sqlite" if settings.is_sqlite else "postgresql"
    features = [
        "boletos-import-inter",
        "boletos-import-inter-zip",
        "boletos-missing-export",
        "purchase-planning-v2",
        "cookie-auth",
        "mfa-totp",
        "security-alerts",
        "alembic-ready",
        "postgres-cutover",
    ]
    if settings.allow_header_auth:
        features.append("header-auth-fallback")
    return InstanceInfo(
        app="gestor-financeiro",
        api="v1",
        app_mode=settings.app_mode,
        auth_mode="cookie",
        backup_mode=settings.backup_mode,
        database_backend=database_backend,
        mfa_required=settings.require_mfa,
        purchase_planning_enabled=True,
        features=features,
    )


@router.get("/overview", response_model=ProjectOverview)
def get_overview() -> ProjectOverview:
    return ProjectOverview(
        stack=[
            "FastAPI",
            "SQLAlchemy",
            "SQLite/PostgreSQL",
            "React",
            "Vite",
            "Tauri (planejado)",
        ],
        modules=[
            ModuleCard(
                key="security",
                title="Seguranca e Acesso",
                description="Usuarios, perfis, parametros da empresa e trilha de auditoria.",
                status="foundation",
            ),
            ModuleCard(
                key="finance",
                title="Lancamentos Financeiros",
                description="Receitas, despesas, recorrencias, transferencias e separacao de juros.",
                status="planned",
            ),
            ModuleCard(
                key="imports",
                title="Importacoes",
                description="OFX, faturamento Linx e faturas a receber.",
                status="planned",
            ),
            ModuleCard(
                key="cashflow",
                title="Fluxo de Caixa",
                description="Saldo atual, previsto, realizado e planejamento mensal.",
                status="planned",
            ),
            ModuleCard(
                key="reports",
                title="DRE e DRO",
                description="Motor de relatorios por competencia com visual alinhado aos modelos atuais.",
                status="planned",
            ),
            ModuleCard(
                key="reconciliation",
                title="Conciliacao Bancaria",
                description="Vinculo entre previsto, realizado e movimentos do OFX.",
                status="planned",
            ),
        ],
        data_sources=[
            DataSource(
                name="OFX Bancario",
                purpose="Realizado bancario e conciliacao",
                owner="Sistema",
            ),
            DataSource(
                name="Linx Faturamento",
                purpose="Receita, markup, descontos e CMV",
                owner="Sistema Externo",
            ),
            DataSource(
                name="Linx Faturas a Receber",
                purpose="Entradas previstas no fluxo de caixa",
                owner="Sistema Externo",
            ),
            DataSource(
                name="Lancamentos Internos",
                purpose="Despesas, receitas manuais, recorrencias e encargos financeiros",
                owner="Gestor Financeiro",
            ),
        ],
    )


@router.post("/client-error", status_code=status.HTTP_204_NO_CONTENT)
def post_client_error(payload: ClientErrorLogCreate, request: Request) -> Response:
    log_client_issue(
        {
            "source": payload.source,
            "message": payload.message,
            "path": payload.path,
            "method": payload.method,
            "status_code": payload.status_code,
            "request_url": payload.request_url,
            "api_base": payload.api_base,
            "details": payload.details,
            "screen": payload.screen,
            "user_agent": payload.user_agent or request.headers.get("user-agent"),
            "client": request.client.host if request.client else None,
            "referer": request.headers.get("referer"),
        }
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

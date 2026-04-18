from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.services.backup import ensure_startup_backup
from app.services.bootstrap import ensure_company_security, ensure_default_company
from app.services.db_schema import ensure_schema_updates
from app.services.error_logging import log_http_issue, log_unhandled_exception, write_route_manifest


FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
RESERVED_API_DOC_PATHS = {"docs", "redoc", "openapi.json"}


def configure_frontend_routes(app: FastAPI, *, blocked_paths: set[str] | None = None) -> None:
    def resolve_frontend_response(full_path: str) -> FileResponse:
        if not FRONTEND_DIST_DIR.exists():
            raise HTTPException(status_code=404, detail="Frontend build not found")

        normalized_path = full_path.strip("/")
        if blocked_paths and normalized_path in blocked_paths:
            raise HTTPException(status_code=404, detail="Not Found")

        requested_path = (FRONTEND_DIST_DIR / full_path).resolve()
        try:
            requested_path.relative_to(FRONTEND_DIST_DIR.resolve())
        except ValueError as exc:  # pragma: no cover - path traversal safeguard
            raise HTTPException(status_code=404, detail="Not Found") from exc

        if full_path and requested_path.is_file():
            return FileResponse(requested_path)

        index_path = FRONTEND_DIST_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="Frontend index not found")

        return FileResponse(index_path)

    @app.get("/", include_in_schema=False)
    async def serve_frontend_root() -> FileResponse:
        return resolve_frontend_response("")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str) -> FileResponse:
        return resolve_frontend_response(full_path)


def create_app() -> FastAPI:
    settings = get_settings()
    cors_origins = list(settings.cors_origins)
    if settings.public_origin and settings.public_origin not in cors_origins:
        cors_origins.append(settings.public_origin)
    docs_enabled = settings.resolved_api_docs_enabled

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def capture_request_errors(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - safeguard at runtime
            log_unhandled_exception(request, exc)
            return JSONResponse(status_code=500, content={"detail": "Erro interno no servidor"})

        if response.status_code >= 400:
            log_http_issue(request, status_code=response.status_code)

        if settings.is_server_mode:
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
            response.headers.setdefault("Cache-Control", "no-store")

        return response

    app.include_router(api_router, prefix=settings.api_prefix)
    configure_frontend_routes(
        app,
        blocked_paths=RESERVED_API_DOC_PATHS if not docs_enabled else None,
    )

    @app.on_event("startup")
    def on_startup() -> None:
        if settings.is_sqlite and not settings.is_server_mode:
            ensure_schema_updates(engine)
            Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            company = ensure_default_company(db)
            ensure_company_security(db, company)
            db.commit()
        ensure_startup_backup()
        write_route_manifest(app)

    return app


app = create_app()

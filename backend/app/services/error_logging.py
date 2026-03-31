from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG_PATH = RUNTIME_DIR / "backend.error.log"
CLIENT_ERROR_LOG_PATH = RUNTIME_DIR / "client.error.log"
ROUTE_LOG_PATH = RUNTIME_DIR / "backend.routes.log"


def _build_rotating_handler(path: Path) -> RotatingFileHandler:
    handler = RotatingFileHandler(path, maxBytes=1_500_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    return handler


def _configure_logger(name: str, path: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "") == str(path) for handler in logger.handlers):
        logger.addHandler(_build_rotating_handler(path))

    return logger


backend_error_logger = _configure_logger("gestor_financeiro.backend", ERROR_LOG_PATH)
client_error_logger = _configure_logger("gestor_financeiro.client", CLIENT_ERROR_LOG_PATH)


def request_context(request: Request) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query or ""),
        "client": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "referer": request.headers.get("referer"),
    }


def log_http_issue(
    request: Request,
    *,
    status_code: int,
    detail: str | None = None,
    level: int = logging.WARNING,
) -> None:
    payload = request_context(request)
    payload["status_code"] = status_code
    if detail:
        payload["detail"] = detail
    backend_error_logger.log(level, json.dumps(payload, ensure_ascii=False))


def log_unhandled_exception(request: Request, exc: Exception) -> None:
    payload = request_context(request)
    payload["error"] = str(exc)
    backend_error_logger.exception(json.dumps(payload, ensure_ascii=False))


def log_client_issue(payload: dict[str, Any]) -> None:
    client_error_logger.warning(json.dumps(payload, ensure_ascii=False))


def write_route_manifest(app: FastAPI) -> None:
    routes: list[dict[str, Any]] = []
    for route in app.routes:
        methods = sorted(method for method in (route.methods or set()) if method not in {"HEAD", "OPTIONS"})
        routes.append(
            {
                "path": getattr(route, "path", ""),
                "name": getattr(route, "name", ""),
                "methods": methods,
            }
        )

    ROUTE_LOG_PATH.write_text(json.dumps(routes, ensure_ascii=False, indent=2), encoding="utf-8")
    backend_error_logger.info(
        json.dumps(
            {
                "event": "startup-route-manifest",
                "route_count": len(routes),
                "route_log_path": str(ROUTE_LOG_PATH),
            },
            ensure_ascii=False,
        )
    )

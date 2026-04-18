import sys
import os
from pathlib import Path

# Adiciona o diretorio do backend ao sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.append(str(backend_dir))

try:
    from app.core.config import get_settings
    print("==> Tentando carregar Settings...")
    settings = get_settings()
    print("==> Settings carregadas com sucesso!")
    print(f"APP_MODE: {settings.app_mode}")
    print(f"DATABASE_URL: {settings.database_url.split('@')[-1]}") # Esconde credenciais
except Exception as e:
    print(f"==> ERRO NA INICIALIZACAO: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent
external_env_path = repo_root.parent / "salomao-config" / "backend.env"
legacy_env_path = repo_root / "backend" / ".env"
env_path = external_env_path if external_env_path.exists() else legacy_env_path
with open(env_path, "r") as f:
    text = f.read()

text = text.replace(
    "PUBLIC_ORIGIN=https://dev.raquel-talita.vps-kinghost.net",
    "PUBLIC_ORIGIN=https://salomao-vps.tail2033b8.ts.net"
)

with open(env_path, "w") as f:
    f.write(text)
print("Updated .env file successfully.")

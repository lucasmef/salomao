from pathlib import Path

repo_root = Path(__file__).resolve().parent
external_env_path = repo_root.parent / "salomao-config" / "backend.env"
legacy_env_path = repo_root / "backend" / ".env"
env_path = external_env_path if external_env_path.exists() else legacy_env_path

legacy_dev_origins = {
    "https://dev.raquel-talita.vps-kinghost.net",
}
tailscale_dev_origin = "https://salomao-vps.tail2033b8.ts.net"

text = env_path.read_text(encoding="utf-8")

for origin in legacy_dev_origins:
    text = text.replace(
        f"PUBLIC_ORIGIN={origin}",
        f"PUBLIC_ORIGIN={tailscale_dev_origin}",
    )

env_path.write_text(text, encoding="utf-8")
print(f"Updated runtime env at {env_path}")

from __future__ import annotations

import ctypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import pystray
from PIL import Image


CREATE_FLAGS = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW


def resolve_project_root() -> Path:
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    if (base_dir / "backend").exists() and (base_dir / "frontend").exists():
        return base_dir

    parent_dir = base_dir.parent
    if (parent_dir / "backend").exists() and (parent_dir / "frontend").exists():
        return parent_dir

    return base_dir


PROJECT_ROOT = resolve_project_root()
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
SCRIPTS_POWERSHELL_DIR = PROJECT_ROOT / "scripts" / "powershell"
PYTHON_EXE = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
POWERSHELL_EXE = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NPM_CMD = Path(r"C:\Program Files\nodejs\npm.cmd")
TAILSCALE_EXE = Path(r"C:\Program Files\Tailscale\tailscale.exe")
ICON_PATH = PROJECT_ROOT / "salomao-s.ico"
BACKEND_PID_FILE = RUNTIME_DIR / "backend.pid"
BACKEND_PORT_FILE = RUNTIME_DIR / "backend-port.txt"
BACKEND_LOG_FILE = RUNTIME_DIR / "backend.out.log"
BACKEND_ERROR_LOG_FILE = RUNTIME_DIR / "backend.err.log"
FRONTEND_BUILD_LOG_FILE = RUNTIME_DIR / "frontend-build.out.log"
FRONTEND_BUILD_ERROR_LOG_FILE = RUNTIME_DIR / "frontend-build.err.log"
TAILSCALE_HTTPS_PORT_FILE = RUNTIME_DIR / "tailscale-https-port.txt"
CONNECT_TAILSCALE_SCRIPT = SCRIPTS_POWERSHELL_DIR / "conectar-tailscale.ps1"
DISCONNECT_TAILSCALE_SCRIPT = SCRIPTS_POWERSHELL_DIR / "desconectar-tailscale.ps1"
ACTIVE_BACKEND_PORTS = [18080, 18081, 18082, 18083, 18084, 18085, 18086, 18087]
LEGACY_BACKEND_PORTS = [8000, 8001, 8002, 8003, 8010, 8011, 8012, 8013, 8014, 8015]
PROJECT_BACKEND_PORTS = ACTIVE_BACKEND_PORTS + [port for port in LEGACY_BACKEND_PORTS if port not in ACTIVE_BACKEND_PORTS]


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def read_first_line(path: Path) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[0].strip() if lines else ""


def write_text(path: Path, value: str) -> None:
    ensure_runtime_dir()
    path.write_text(value, encoding="utf-8")


def remove_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def terminate_pid(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_FLAGS,
        check=False,
    )


def wait_http_ready(url: str, attempts: int = 40, delay_seconds: float = 0.5) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=3):
                return True
        except urllib.error.HTTPError as exc:
            if 200 <= exc.code < 500:
                return True
        except Exception:
            time.sleep(delay_seconds)
    return False


def backend_health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/api/v1/health"


def request_url(url: str, timeout: float = 3.0) -> tuple[int, bytes, dict[str, str]] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status_code = getattr(response, "status", 200)
            body = response.read()
            headers = dict(response.info().items())
            return status_code, body, headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())
    except Exception:
        return None


def panel_ready(port: int) -> bool:
    response = request_url(f"http://127.0.0.1:{port}/")
    if response is None:
        return False
    status_code, body, headers = response
    content_type = headers.get("Content-Type", "")
    return status_code == 200 and ("text/html" in content_type.lower() or b"<!doctype html" in body.lower())


def project_backend_state(port: int) -> tuple[bool, bool]:
    response = request_url(backend_health_url(port), timeout=1.5)
    if response is None:
        return False, False
    status_code, body, _headers = response
    if status_code != 200 or b'"status"' not in body:
        return False, False
    return True, panel_ready(port)


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def candidate_scan_ports() -> list[int]:
    preferred = read_first_line(BACKEND_PORT_FILE)
    ordered: list[int] = []
    if preferred.isdigit():
        preferred_port = int(preferred)
        if preferred_port in PROJECT_BACKEND_PORTS:
            ordered.append(preferred_port)

    for port in PROJECT_BACKEND_PORTS:
        if port not in ordered:
            ordered.append(port)
    return ordered


def listener_pids_for_port(port: int) -> list[int]:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=CREATE_FLAGS,
        check=False,
    )
    if result.returncode != 0:
        return []

    pids: set[int] = set()
    pattern = re.compile(rf"^\s*TCP\s+127\.0\.0\.1:{port}\s+\S+\s+\S+\s+(\d+)\s*$", re.IGNORECASE)
    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        pid = int(match.group(1))
        if pid > 0:
            pids.add(pid)
    return sorted(pids)


def cleanup_project_backends(include_ready: bool) -> list[int]:
    stopped_ports: list[int] = []
    seen_ports: set[int] = set()

    for port in candidate_scan_ports():
        if port in seen_ports:
            continue
        seen_ports.add(port)

        detected, ready = project_backend_state(port)
        if not detected:
            continue
        if ready and not include_ready:
            continue

        pids = listener_pids_for_port(port)
        if not pids:
            continue

        for pid in pids:
            terminate_pid(pid)

        deadline = time.time() + 8
        while time.time() < deadline:
            if port_available(port):
                stopped_ports.append(port)
                break
            time.sleep(0.2)

    if stopped_ports:
        remove_if_exists(BACKEND_PID_FILE)
        remove_if_exists(BACKEND_PORT_FILE)

    return stopped_ports


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def format_script_failure(output: str, fallback_message: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return fallback_message
    return lines[-1]


def run_powershell_script(script_path: Path, args: list[str] | None = None, elevate: bool = False) -> str:
    if not POWERSHELL_EXE.exists():
        raise RuntimeError("Nao encontrei o PowerShell do Windows para executar a automacao.")
    if not script_path.exists():
        raise RuntimeError(f"Script nao encontrado em '{script_path}'.")

    script_args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    if args:
        script_args.extend(args)

    if elevate:
        quoted_args = ", ".join(ps_quote(item) for item in script_args)
        command = [
            str(POWERSHELL_EXE),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f"$p = Start-Process -FilePath {ps_quote(str(POWERSHELL_EXE))} "
                f"-Verb RunAs -ArgumentList @({quoted_args}) -PassThru -Wait; "
                "exit $p.ExitCode"
            ),
        ]
    else:
        command = [str(POWERSHELL_EXE), *script_args]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=CREATE_FLAGS,
        check=False,
    )
    output = result.stdout.strip()
    if result.returncode != 0:
        raise RuntimeError(format_script_failure(output, f"Falha ao executar '{script_path.name}'.")) from None
    return output


def current_tailscale_publish() -> tuple[str, int | None] | None:
    if not TAILSCALE_EXE.exists():
        return None

    result = subprocess.run(
        [str(TAILSCALE_EXE), "serve", "status"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=CREATE_FLAGS,
        check=False,
    )
    if result.returncode != 0:
        return None

    published_url: str | None = None
    proxy_port: int | None = None

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if published_url is None:
            url_match = re.match(r"^(https://\S+)\s+\(tailnet only\)$", line)
            if url_match:
                published_url = url_match.group(1)
                continue

        if proxy_port is None:
            port_match = re.match(r"^\|--\s+/\s+proxy\s+http://127\.0\.0\.1:(\d+)$", line)
            if port_match:
                proxy_port = int(port_match.group(1))

    if published_url is None:
        return None

    return published_url, proxy_port


def resolve_backend_port() -> int:
    preferred = read_first_line(BACKEND_PORT_FILE)
    if preferred.isdigit():
        preferred_port = int(preferred)
        if preferred_port in ACTIVE_BACKEND_PORTS and port_available(preferred_port):
            return preferred_port

    for port in ACTIVE_BACKEND_PORTS:
        if port_available(port):
            return port
    raise RuntimeError("Nao encontrei uma porta livre para iniciar o backend.")


def current_backend_port() -> int | None:
    for port in candidate_scan_ports():
        detected, ready = project_backend_state(port)
        if detected and ready:
            write_text(BACKEND_PORT_FILE, str(port))
            return port
    return None


def current_backend_pid() -> int | None:
    raw_pid = read_first_line(BACKEND_PID_FILE)
    if not raw_pid.isdigit():
        return None
    pid = int(raw_pid)
    return pid if pid_is_running(pid) else None


def build_frontend() -> None:
    if not PYTHON_EXE.exists():
        raise RuntimeError(f"Python do backend nao encontrado em '{PYTHON_EXE}'.")
    if not NPM_CMD.exists():
        raise RuntimeError("Nao encontrei o npm.cmd em C:\\Program Files\\nodejs.")
    if not (FRONTEND_DIR / "node_modules").exists():
        raise RuntimeError("Dependencias do frontend nao encontradas. Rode npm install antes de usar o controle.")

    ensure_runtime_dir()
    env = os.environ.copy()
    env["VITE_API_URL"] = "/api/v1"
    with FRONTEND_BUILD_LOG_FILE.open("wb") as stdout_handle, FRONTEND_BUILD_ERROR_LOG_FILE.open("wb") as stderr_handle:
        result = subprocess.run(
            [str(NPM_CMD), "run", "build"],
            cwd=FRONTEND_DIR,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=CREATE_FLAGS,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError("Falha ao gerar a interface local. Veja os logs de build em .runtime.")


def start_backend(port: int) -> int:
    ensure_runtime_dir()
    command = [
        str(PYTHON_EXE),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    stdout_handle = BACKEND_LOG_FILE.open("wb")
    stderr_handle = BACKEND_ERROR_LOG_FILE.open("wb")
    process = subprocess.Popen(
        command,
        cwd=BACKEND_DIR,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=CREATE_FLAGS,
    )
    stdout_handle.close()
    stderr_handle.close()
    return process.pid


def stop_backend() -> None:
    pid = current_backend_pid()
    if pid is not None:
        terminate_pid(pid)
        deadline = time.time() + 10
        while time.time() < deadline and pid_is_running(pid):
            time.sleep(0.2)
    cleanup_project_backends(include_ready=True)
    remove_if_exists(BACKEND_PID_FILE)
    remove_if_exists(BACKEND_PORT_FILE)


class ControlApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Controle do Sistema Salomao")
        self.root.geometry("520x320")
        self.root.minsize(520, 320)
        self.root.maxsize(520, 320)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_requested)
        self.root.bind("<Unmap>", self.on_window_unmap)
        if ICON_PATH.exists():
            try:
                self.root.iconbitmap(default=str(ICON_PATH))
            except Exception:
                pass

        self.status_var = tk.StringVar(value="Preparando...")
        self.detail_var = tk.StringVar(value="Abrindo controle local sem console.")
        self.url_var = tk.StringVar(value="URL local: aguardando inicializacao")
        self.remote_var = tk.StringVar(value="Tailscale remoto: desconectado")
        self.remote_url_var = tk.StringVar(value="URL remota: nao publicada")
        self.busy = False
        self.tray_icon: pystray.Icon | None = None
        self.tray_thread: threading.Thread | None = None
        self.tray_active = False
        self.window_hidden = False

        self._build_layout()
        self.root.after(200, lambda: self.start_system(open_browser=True))
        self.root.after(2000, self.refresh_status)

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=18)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Sistema Salomao", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text="Minimize esta janela para manter o sistema ativo na bandeja do Windows.",
            wraplength=470,
        ).pack(anchor="w", pady=(6, 14))

        status_box = ttk.Frame(container)
        status_box.pack(fill="x")
        ttk.Label(status_box, textvariable=self.status_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(status_box, textvariable=self.detail_var, wraplength=470).pack(anchor="w", pady=(4, 0))
        ttk.Label(status_box, textvariable=self.url_var).pack(anchor="w", pady=(8, 0))
        ttk.Separator(container).pack(fill="x", pady=(16, 12))

        remote_box = ttk.Frame(container)
        remote_box.pack(fill="x")
        ttk.Label(remote_box, text="Acesso remoto", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            remote_box,
            text="Conecte e desligue o Tailscale por aqui, sem depender dos atalhos .bat.",
            wraplength=470,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(remote_box, textvariable=self.remote_var).pack(anchor="w", pady=(8, 0))
        ttk.Label(remote_box, textvariable=self.remote_url_var, wraplength=470).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=(20, 0))
        local_buttons = ttk.Frame(buttons)
        local_buttons.pack(fill="x")
        remote_buttons = ttk.Frame(buttons)
        remote_buttons.pack(fill="x", pady=(10, 0))

        self.start_button = ttk.Button(local_buttons, text="Iniciar", command=lambda: self.start_system(open_browser=True))
        self.open_button = ttk.Button(local_buttons, text="Abrir painel", command=self.open_system)
        self.restart_button = ttk.Button(local_buttons, text="Reiniciar", command=self.restart_system)
        self.stop_button = ttk.Button(local_buttons, text="Encerrar", command=self.stop_system)
        self.minimize_button = ttk.Button(local_buttons, text="Minimizar", command=self.minimize_to_tray)
        self.connect_remote_button = ttk.Button(remote_buttons, text="Conectar remoto", command=self.connect_remote)
        self.open_remote_button = ttk.Button(remote_buttons, text="Abrir remoto", command=self.open_remote)
        self.disconnect_remote_button = ttk.Button(
            remote_buttons,
            text="Desconectar remoto",
            command=self.disconnect_remote,
        )

        for widget in (
            self.start_button,
            self.open_button,
            self.restart_button,
            self.stop_button,
            self.minimize_button,
        ):
            widget.pack(side="left", padx=(0, 8))

        for widget in (
            self.connect_remote_button,
            self.open_remote_button,
            self.disconnect_remote_button,
        ):
            widget.pack(side="left", padx=(0, 8))

    def load_tray_image(self) -> Image.Image:
        if ICON_PATH.exists():
            return Image.open(ICON_PATH)

        return Image.new("RGBA", (64, 64), color=(24, 82, 140, 255))

    def update_tray_title(self) -> None:
        if self.tray_icon is None:
            return

        port = current_backend_port()
        remote_publish = current_tailscale_publish()
        lines = ["Sistema Salomao"]
        if port is None:
            lines.append("Sistema parado")
        else:
            lines.append(f"Sistema ativo em http://127.0.0.1:{port}")
        if remote_publish is not None:
            lines.append(f"Remoto ativo em {remote_publish[0]}")
        self.tray_icon.title = "\n".join(lines)

    def ensure_tray_icon(self) -> None:
        if self.tray_icon is not None:
            return

        menu = pystray.Menu(
            pystray.MenuItem("Mostrar controle", self.on_tray_show_control, default=True),
            pystray.MenuItem("Abrir painel", self.on_tray_open_panel),
            pystray.MenuItem("Conectar remoto", self.on_tray_connect_remote),
            pystray.MenuItem("Abrir remoto", self.on_tray_open_remote),
            pystray.MenuItem("Desconectar remoto", self.on_tray_disconnect_remote),
            pystray.MenuItem("Reiniciar sistema", self.on_tray_restart_system),
            pystray.MenuItem("Encerrar sistema", self.on_tray_stop_system),
            pystray.MenuItem("Sair", self.on_tray_exit_application),
        )
        self.tray_icon = pystray.Icon("sistema_salomao", self.load_tray_image(), "Sistema Salomao", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()
        self.tray_active = True
        self.update_tray_title()

    def stop_tray_icon(self) -> None:
        if self.tray_icon is None:
            return

        try:
            self.tray_icon.stop()
        except Exception:
            pass
        self.tray_icon = None
        self.tray_thread = None
        self.tray_active = False

    def minimize_to_tray(self) -> None:
        self.ensure_tray_icon()
        self.window_hidden = True
        self.root.withdraw()
        self.update_tray_title()

    def restore_from_tray(self) -> None:
        self.window_hidden = False
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()
        self.update_tray_title()

    def on_tray_show_control(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.restore_from_tray)

    def on_tray_open_panel(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.open_system)

    def on_tray_restart_system(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.restart_system)

    def on_tray_stop_system(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.stop_system)

    def on_tray_connect_remote(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.connect_remote)

    def on_tray_open_remote(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.open_remote)

    def on_tray_disconnect_remote(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.disconnect_remote)

    def on_tray_exit_application(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.exit_application)

    def on_window_unmap(self, _event=None) -> None:
        if self.window_hidden:
            return
        if self.root.state() == "iconic":
            self.root.after(0, self.minimize_to_tray)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self.start_button,
            self.open_button,
            self.restart_button,
            self.stop_button,
            self.minimize_button,
            self.connect_remote_button,
            self.open_remote_button,
            self.disconnect_remote_button,
        ):
            widget.configure(state=state)

    def run_async(self, worker, on_success=None, on_error=None) -> None:
        if self.busy:
            return

        self.set_busy(True)

        def wrapped() -> None:
            try:
                result = worker()
            except Exception as exc:
                self.root.after(0, lambda: self._finish_with_error(str(exc), on_error))
                return
            self.root.after(0, lambda: self._finish_with_success(result, on_success))

        threading.Thread(target=wrapped, daemon=True).start()

    def _finish_with_success(self, result, on_success) -> None:
        self.set_busy(False)
        if on_success is not None:
            on_success(result)
        self.refresh_status()

    def _finish_with_error(self, message: str, on_error) -> None:
        self.set_busy(False)
        self.status_var.set("Falha na operacao")
        self.detail_var.set(message)
        if on_error is not None:
            on_error(message)
        else:
            messagebox.showerror("Sistema Salomao", message)
        self.refresh_status()

    def start_system(self, open_browser: bool = False) -> None:
        def worker() -> int:
            running_port = current_backend_port()
            if running_port is not None:
                return running_port

            self.root.after(0, lambda: self.status_var.set("Limpando inicializacoes antigas..."))
            self.root.after(
                0,
                lambda: self.detail_var.set("Removendo backends antigos presos nas portas locais do Salomao."),
            )
            cleanup_project_backends(include_ready=False)

            running_port = current_backend_port()
            if running_port is not None:
                return running_port

            self.root.after(0, lambda: self.status_var.set("Gerando interface local..."))
            self.root.after(
                0,
                lambda: self.detail_var.set("Compilando o frontend para servir tudo no mesmo endereco local."),
            )
            build_frontend()

            port = resolve_backend_port()
            self.root.after(0, lambda: self.status_var.set("Iniciando backend..."))
            self.root.after(0, lambda: self.detail_var.set(f"Subindo servidor local na porta {port}."))
            pid = start_backend(port)
            write_text(BACKEND_PID_FILE, str(pid))
            write_text(BACKEND_PORT_FILE, str(port))

            if not wait_http_ready(f"http://127.0.0.1:{port}/api/v1/health", attempts=50, delay_seconds=0.5):
                stop_backend()
                raise RuntimeError("O backend nao respondeu depois da inicializacao. Veja os logs em .runtime.")
            if not panel_ready(port):
                stop_backend()
                raise RuntimeError("O backend respondeu, mas a interface nao abriu na raiz local. Veja os logs em .runtime.")

            return port

        def on_success(port: int) -> None:
            self.status_var.set("Sistema ativo")
            self.detail_var.set("Controle local aberto. Voce pode minimizar para a bandeja sem derrubar o sistema.")
            self.url_var.set(f"URL local: http://127.0.0.1:{port}")
            self.update_tray_title()
            if open_browser:
                webbrowser.open(f"http://127.0.0.1:{port}")

        self.run_async(worker, on_success=on_success)

    def stop_system(self) -> None:
        def worker() -> None:
            stop_backend()

        def on_success(_: None) -> None:
            self.status_var.set("Sistema encerrado")
            self.detail_var.set("O backend local foi parado.")
            self.url_var.set("URL local: sistema parado")
            self.update_tray_title()

        self.run_async(worker, on_success=on_success)

    def connect_remote(self) -> None:
        def worker() -> tuple[str, int | None]:
            self.root.after(0, lambda: self.status_var.set("Conectando acesso remoto..."))
            self.root.after(
                0,
                lambda: self.detail_var.set("O Windows pode pedir permissao de administrador para publicar no Tailscale."),
            )
            run_powershell_script(CONNECT_TAILSCALE_SCRIPT, args=["-NoBuild"], elevate=True)
            publish = current_tailscale_publish()
            if publish is None:
                raise RuntimeError("O Tailscale nao confirmou a publicacao remota depois da conexao.")
            return publish

        def on_success(result: tuple[str, int | None]) -> None:
            published_url, proxy_port = result
            self.remote_var.set("Tailscale remoto: ativo")
            self.remote_url_var.set(f"URL remota: {published_url}")
            if proxy_port is None:
                self.detail_var.set("A publicacao remota foi ativada pelo Tailscale.")
            else:
                self.detail_var.set(f"Acesso remoto ativo pelo Tailscale apontando para a porta local {proxy_port}.")
            self.update_tray_title()

        self.run_async(worker, on_success=on_success)

    def disconnect_remote(self) -> None:
        def worker() -> None:
            self.root.after(0, lambda: self.status_var.set("Desconectando acesso remoto..."))
            self.root.after(
                0,
                lambda: self.detail_var.set("O Windows pode pedir permissao de administrador para desligar a publicacao."),
            )
            run_powershell_script(DISCONNECT_TAILSCALE_SCRIPT, elevate=True)

        def on_success(_: None) -> None:
            self.remote_var.set("Tailscale remoto: desconectado")
            self.remote_url_var.set("URL remota: nao publicada")
            self.detail_var.set("A publicacao do Tailscale foi desligada.")
            self.update_tray_title()

        self.run_async(worker, on_success=on_success)

    def restart_system(self) -> None:
        def worker() -> int:
            stop_backend()
            self.root.after(0, lambda: self.status_var.set("Limpando inicializacoes antigas..."))
            self.root.after(
                0,
                lambda: self.detail_var.set("Garantindo que nao restou nenhum backend antigo antes do reinicio."),
            )
            cleanup_project_backends(include_ready=True)
            build_frontend()
            port = resolve_backend_port()
            pid = start_backend(port)
            write_text(BACKEND_PID_FILE, str(pid))
            write_text(BACKEND_PORT_FILE, str(port))
            if not wait_http_ready(f"http://127.0.0.1:{port}/api/v1/health", attempts=50, delay_seconds=0.5):
                stop_backend()
                raise RuntimeError("O backend nao voltou a responder depois do reinicio.")
            if not panel_ready(port):
                stop_backend()
                raise RuntimeError("O backend voltou, mas a interface nao abriu na raiz local.")
            return port

        def on_success(port: int) -> None:
            self.status_var.set("Sistema reiniciado")
            self.detail_var.set("O backend local voltou a responder normalmente.")
            self.url_var.set(f"URL local: http://127.0.0.1:{port}")
            self.update_tray_title()
            webbrowser.open(f"http://127.0.0.1:{port}")

        self.run_async(worker, on_success=on_success)

    def open_system(self) -> None:
        port = current_backend_port()
        if port is None:
            if messagebox.askyesno("Sistema Salomao", "O sistema nao esta ativo. Deseja iniciar agora?"):
                self.start_system(open_browser=True)
            return
        webbrowser.open(f"http://127.0.0.1:{port}")

    def open_remote(self) -> None:
        publish = current_tailscale_publish()
        if publish is None:
            if messagebox.askyesno(
                "Sistema Salomao",
                "O acesso remoto nao esta publicado. Deseja conectar agora pelo Tailscale?",
            ):
                self.connect_remote()
            return
        webbrowser.open(publish[0])

    def refresh_remote_status(self) -> None:
        publish = current_tailscale_publish()
        port = current_backend_port()
        if publish is None:
            self.remote_var.set("Tailscale remoto: desconectado")
            self.remote_url_var.set("URL remota: nao publicada")
            return

        published_url, proxy_port = publish
        if port is None and proxy_port is not None:
            self.remote_var.set(f"Tailscale remoto: publicado, mas o backend local da porta {proxy_port} esta parado")
        elif proxy_port is not None and port is not None and proxy_port == port:
            self.remote_var.set("Tailscale remoto: ativo")
        elif proxy_port is not None:
            self.remote_var.set(f"Tailscale remoto: ativo, mas apontando para a porta {proxy_port}")
        else:
            self.remote_var.set("Tailscale remoto: ativo")
        self.remote_url_var.set(f"URL remota: {published_url}")

    def refresh_status(self) -> None:
        if not self.busy:
            port = current_backend_port()
            if port is None:
                self.status_var.set("Sistema parado")
                self.detail_var.set("Use Iniciar para subir o backend local. O controle pode ficar minimizado na bandeja.")
                self.url_var.set("URL local: sistema parado")
            else:
                self.status_var.set("Sistema ativo")
                self.detail_var.set("O controle pode ficar minimizado na bandeja enquanto o sistema roda.")
                self.url_var.set(f"URL local: http://127.0.0.1:{port}")
            self.refresh_remote_status()
            self.update_tray_title()
        self.root.after(5000, self.refresh_status)

    def on_close_requested(self) -> None:
        if self.busy:
            messagebox.showinfo("Sistema Salomao", "Aguarde a operacao atual terminar.")
            return

        self.minimize_to_tray()

    def exit_application(self) -> None:
        if self.busy:
            messagebox.showinfo("Sistema Salomao", "Aguarde a operacao atual terminar.")
            return

        port = current_backend_port()
        if port is not None:
            confirmed = messagebox.askyesno(
                "Sistema Salomao",
                "Sair tambem vai encerrar o sistema local. Deseja continuar?",
            )
            if not confirmed:
                return

            def worker() -> None:
                stop_backend()

            def on_success(_: None) -> None:
                self.stop_tray_icon()
                self.root.destroy()

            self.run_async(worker, on_success=on_success, on_error=lambda _message: self.root.destroy())
            return

        self.stop_tray_icon()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    ensure_runtime_dir()
    ControlApp().run()

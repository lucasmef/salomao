from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


DETACHED_FLAGS = (
    subprocess.CREATE_NEW_PROCESS_GROUP
    | subprocess.DETACHED_PROCESS
    | subprocess.CREATE_NO_WINDOW
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch a background process detached from the current console."
    )
    parser.add_argument("--cwd", required=True, help="Working directory for the child process.")
    parser.add_argument("--stdout", required=True, help="File path for stdout redirection.")
    parser.add_argument("--stderr", required=True, help="File path for stderr redirection.")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Environment variable override in the form NAME=value.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to launch after --.")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command to execute")
    return args


def build_environment(overrides: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"Invalid environment override: {item!r}")
        key, value = item.split("=", 1)
        env[key] = value
    return env


def ensure_parent(path_text: str) -> None:
    Path(path_text).parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    env = build_environment(args.env)

    ensure_parent(args.stdout)
    ensure_parent(args.stderr)

    with open(args.stdout, "ab", buffering=0) as stdout_handle, open(
        args.stderr, "ab", buffering=0
    ) as stderr_handle:
        process = subprocess.Popen(
            args.command,
            cwd=args.cwd,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=DETACHED_FLAGS,
        )

    sys.stdout.write(str(process.pid))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

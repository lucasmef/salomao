#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV_FILES = {
    "backend/.env.example",
    "backend/.env.dev.example",
    "backend/.env.prod.example",
}
BLOCKED_PATH_PREFIXES = (
    ".runtime/",
    "artifacts/",
    "backend/backups/",
    "backups/",
)
BLOCKED_GLOBS = (
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*.cer",
    "*.jks",
    "*.db",
    "*.db-shm",
    "*.db-wal",
    "*.sqlite",
    "*.sqlite-shm",
    "*.sqlite-wal",
    "*.sqlite3",
    "*.sqlite3-shm",
    "*.sqlite3-wal",
    "*.dump",
    "*.bak",
    "*.backup",
    "*.log",
)
TEXT_SUFFIX_ALLOWLIST = {
    ".css",
    ".html",
    ".hujson",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yml",
    ".yaml",
}
SECRET_PATTERNS = (
    ("AWS access key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(rb"\b(?:ghp|gho)_[A-Za-z0-9]{20,}\b")),
    ("GitHub fine-grained token", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("Google API key", re.compile(rb"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Private key block", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [item for item in result.stdout.decode("utf-8", errors="ignore").split("\0") if item]


def is_blocked_env_file(path: str) -> bool:
    path_obj = Path(path)
    if not path_obj.name.startswith(".env"):
        return False
    return path not in ALLOWED_ENV_FILES


def is_blocked_path(path: str) -> str | None:
    if is_blocked_env_file(path):
        return "tracked environment file"
    for prefix in BLOCKED_PATH_PREFIXES:
        if path.startswith(prefix):
            return f"blocked path prefix: {prefix}"
    for pattern in BLOCKED_GLOBS:
        if fnmatch.fnmatch(path, pattern):
            return f"blocked file pattern: {pattern}"
    return None


def should_scan_contents(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in TEXT_SUFFIX_ALLOWLIST or suffix == ""


def scan_file_contents(path: str) -> list[str]:
    if not should_scan_contents(path):
        return []
    payload = (REPO_ROOT / path).read_bytes()
    if b"\0" in payload:
        return []
    findings: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(payload):
            findings.append(label)
    return findings


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        blocked_reason = is_blocked_path(path)
        if blocked_reason:
            findings.append(f"{path}: {blocked_reason}")

        for content_finding in scan_file_contents(path):
            findings.append(f"{path}: matched secret pattern ({content_finding})")

    if findings:
        print("Security scan failed. Sensitive files or high-confidence secret patterns were found:")
        for finding in findings:
            print(f" - {finding}")
        return 1

    print("Security scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

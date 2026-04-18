from __future__ import annotations

import subprocess
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_GMAIL_SETUP_SCRIPT = _PROJECT_ROOT / "scripts" / "gmail_setup.py"


def launch_gmail_setup(client_id: str, client_secret: str, account_label: str) -> None:
    command = [
        str(_resolve_setup_python()),
        str(_GMAIL_SETUP_SCRIPT),
        "--client-id",
        client_id,
        "--client-secret",
        client_secret,
        "--account-label",
        account_label,
    ]
    subprocess.Popen(
        command,
        cwd=str(_PROJECT_ROOT),
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )


def _resolve_setup_python() -> Path:
    venv_python = _PROJECT_ROOT / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)

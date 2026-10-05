"""Launch a headless coding agent against an incident evidence pack."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(os.getenv("REPO_DIR", Path(__file__).resolve().parent.parent))
BASE_COMMAND = os.getenv(
    "CODING_AGENT_COMMAND",
    "codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox",
)


def _strip_managed_options(args: list[str]) -> list[str]:
    cleaned, skip = [], False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in ("-C", "--cd", "--output-last-message"):
            skip = True
            continue
        cleaned.append(arg)
    if cleaned and cleaned[-1] == "-":
        cleaned.pop()
    return cleaned


def build_prompt(incident_dir: Path, evidence: dict) -> str:
    return f"""
You are an incident-response coding agent.

Repository: {REPO_DIR}
Incident evidence directory: {incident_dir}
(alert.json, incident.md, logs.txt and traces.txt are in that directory)

Alert / evidence summary:
{json.dumps(evidence, indent=2)}

Tasks:
1. Inspect the repository and the evidence files.
2. Identify the root cause of the reported incident.
3. Make the smallest safe code change necessary. Do not make unrelated changes.
4. Do NOT run tests; the system runs them automatically after you finish.
5. Report the root cause, what you changed, and why.

If this is only a responder test (label test=true) and there is no real
incident, do not modify any code and do not run anything. State clearly that
no fix is required. End your final answer with exactly this line:
No fix is required.
"""


def verify_tests(incident_dir: Path) -> None:
    candidates = [
        REPO_DIR / ".venv" / "Scripts" / "python.exe",
        REPO_DIR / ".venv" / "bin" / "python",
    ]
    exe = next((str(path) for path in candidates if path.exists()), sys.executable)
    out = incident_dir / "verification.txt"
    try:
        verify = subprocess.run(
            [exe, "-m", "pytest", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out.write_text(
            f"exit={verify.returncode}\n{verify.stdout}\n{verify.stderr}",
            encoding="utf-8",
        )
    except Exception as exc:
        out.write_text(f"Verification failed to run: {exc!r}\n", encoding="utf-8")


def _write_test_response(incident_dir: Path, evidence: dict) -> dict:
    """Deterministic fallback when Codex is unavailable for a test alert."""
    message = (
        "Responder test notification received.\n"
        f"Alert: {evidence.get('alertname')}\n"
        f"Summary: {evidence.get('summary')}\n"
        "There is no real incident to investigate.\n"
        "No fix is required.\n"
    )
    (incident_dir / "last-message.txt").write_text(message, encoding="utf-8")
    (incident_dir / "agent-response.txt").write_text(
        "Used local test responder because the coding agent CLI was unavailable.\n"
        + message,
        encoding="utf-8",
    )
    return {"started": True, "exit_code": 0, "mode": "local-test"}


def _resolve_command(base: list[str]) -> list[str] | None:
    if not base:
        return None
    exe = base[0]
    found = shutil.which(exe)
    if found is None and os.name == "nt" and not exe.lower().endswith((".exe", ".cmd", ".bat")):
        found = shutil.which(f"{exe}.cmd") or shutil.which(f"{exe}.exe")
    if found is None:
        return None
    return [found, *base[1:]]


def run_agent(incident_dir: Path, evidence: dict) -> dict:
    out = incident_dir / "agent-response.txt"
    is_test = str(evidence.get("test", "")).lower() in {"true", "1", "yes"}
    base = _resolve_command(_strip_managed_options(shlex.split(BASE_COMMAND, posix=os.name != "nt")))

    if base is None:
        if is_test:
            return _write_test_response(incident_dir, evidence)
        out.write_text("Agent command not found on PATH.\n", encoding="utf-8")
        return {"started": False, "exit_code": None, "mode": "missing"}

    command = base + [
        "-C",
        str(REPO_DIR),
        "--output-last-message",
        str(incident_dir / "last-message.txt"),
        "-",
    ]
    prompt = build_prompt(incident_dir, evidence)

    try:
        result = subprocess.run(
            command,
            cwd=REPO_DIR,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=900,
        )
    except Exception as exc:
        if is_test:
            return _write_test_response(incident_dir, evidence)
        out.write_text(f"Agent failed to run: {exc!r}\n", encoding="utf-8")
        return {"started": False, "exit_code": None, "mode": "error"}

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    out.write_text(combined, encoding="utf-8")

    last = incident_dir / "last-message.txt"
    if result.returncode != 0 and is_test and (not last.exists() or not last.read_text(encoding="utf-8").strip()):
        return _write_test_response(incident_dir, evidence)

    if not is_test:
        verify_tests(incident_dir)
    return {"started": True, "exit_code": result.returncode, "mode": "codex"}

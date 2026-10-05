"""Persist alert payloads and kick off evidence collection + agent response."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agent import run_agent
from evidence import collect_evidence

INCIDENTS_DIR = Path(
    os.getenv(
        "INCIDENTS_DIR",
        Path(__file__).resolve().parent / "incidents",
    )
)
INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)


def handle_alert(payload: dict) -> dict:
    timestamp = datetime.now(timezone.utc)
    incident_id = timestamp.strftime("%Y%m%dT%H%M%SZ")
    incident_dir = INCIDENTS_DIR / incident_id
    incident_dir.mkdir(parents=True, exist_ok=True)

    (incident_dir / "alert.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    evidence = collect_evidence(payload=payload, incident_dir=incident_dir)
    agent_result = run_agent(incident_dir=incident_dir, evidence=evidence)

    result = {
        "incident_id": incident_id,
        "agent_started": agent_result["started"],
        "agent_exit_code": agent_result["exit_code"],
        "agent_mode": agent_result.get("mode"),
    }
    (incident_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result

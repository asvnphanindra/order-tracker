"""Collect alert context plus recent logs and traces for an incident."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100/loki")
TEMPO_URL = os.getenv("TEMPO_URL", "http://localhost:3200")


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.load(resp)


def _logs() -> str:
    now = int(time.time())
    query = urllib.parse.urlencode(
        {
            "query": '{service_name="order-tracker"}',
            "start": (now - 900) * 10**9,
            "end": now * 10**9,
            "limit": 200,
        }
    )
    try:
        return json.dumps(_get(f"{LOKI_URL}/api/v1/query_range?{query}"), indent=2)
    except Exception as exc:
        return f"Unable to collect logs: {exc!r}\n"


def _traces() -> str:
    now = int(time.time())
    query = urllib.parse.urlencode(
        {
            "q": '{ resource.service.name = "order-tracker" && status = error }',
            "start": now - 900,
            "end": now,
            "limit": 10,
        }
    )
    try:
        return json.dumps(_get(f"{TEMPO_URL}/api/search?{query}"), indent=2)
    except Exception as exc:
        return f"Unable to collect traces: {exc!r}\n"


def collect_evidence(payload: dict, incident_dir: Path) -> dict:
    alerts = payload.get("alerts", [])
    first = alerts[0] if alerts else {}
    labels = first.get("labels", {})
    annotations = first.get("annotations", {})

    (incident_dir / "logs.txt").write_text(_logs(), encoding="utf-8")
    (incident_dir / "traces.txt").write_text(_traces(), encoding="utf-8")
    (incident_dir / "incident.md").write_text(
        "# Incident\n\n"
        f"- alert: {labels.get('alertname')}\n"
        f"- status: {first.get('status')}\n"
        f"- endpoint: {annotations.get('endpoint', labels.get('http_route'))}\n"
        f"- summary: {annotations.get('summary')}\n"
        f"- dashboard: {annotations.get('dashboard_url')}\n"
        f"- test: {labels.get('test')}\n",
        encoding="utf-8",
    )
    return {
        "alertname": labels.get("alertname"),
        "endpoint": annotations.get("endpoint", labels.get("http_route")),
        "summary": annotations.get("summary"),
        "status": first.get("status"),
        "test": labels.get("test"),
    }

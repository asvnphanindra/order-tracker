#!/usr/bin/env bash
cd "$(dirname "$0")"
exec uv run uvicorn main:app --host 0.0.0.0 --port 8001

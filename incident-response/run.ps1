@param(
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required to run the incident responder"
}

uv pip install -r requirements.txt
uv run --with fastapi --with "uvicorn[standard]" uvicorn main:app --host 0.0.0.0 --port $Port

#!/usr/bin/env bash
set -euo pipefail

# Arranca la API, el MCP y luego el chat interactivo.
# El script se ejecuta desde la carpeta del proyecto.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$ROOT_DIR/.venv/bin/python"
LOG_DIR="$ROOT_DIR/logs"

if [[ ! -x "$VENV_PY" ]]; then
  echo "No encontre la virtualenv en $VENV_PY"
  echo "Primero instala dependencias con Python 3.11 y crea .venv."
  exit 1
fi

mkdir -p "$LOG_DIR"

API_LOG="$LOG_DIR/api.log"
MCP_LOG="$LOG_DIR/mcp.log"
API_URL="http://127.0.0.1:8000/health"
MCP_URL="http://127.0.0.1:8001/health"
WAIT_SECONDS=30

wait_for_health() {
  local url="$1"
  local label="$2"
  local elapsed=0

  while [[ $elapsed -lt $WAIT_SECONDS ]]; do
    if curl -sf --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo "Timeout esperando $label en $url"
  return 1
}

cleanup() {
  if [[ "${API_STARTED:-0}" == "1" ]] && [[ -n "${API_PID:-}" ]] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
  if [[ "${MCP_STARTED:-0}" == "1" ]] && [[ -n "${MCP_PID:-}" ]] && kill -0 "$MCP_PID" 2>/dev/null; then
    kill "$MCP_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if curl -sf --max-time 2 "$API_URL" >/dev/null 2>&1; then
  echo "API REST ya estaba activa en http://127.0.0.1:8000"
else
  echo "Iniciando API REST..."
  "$VENV_PY" "$ROOT_DIR/api.py" >"$API_LOG" 2>&1 &
  API_PID=$!
  API_STARTED=1
fi
wait_for_health "$API_URL" "la API REST"

if curl -sf --max-time 2 "$MCP_URL" >/dev/null 2>&1; then
  echo "Servidor MCP ya estaba activo en http://127.0.0.1:8001"
else
  echo "Iniciando servidor MCP..."
  "$VENV_PY" "$ROOT_DIR/mcp_server.py" >"$MCP_LOG" 2>&1 &
  MCP_PID=$!
  MCP_STARTED=1
fi
wait_for_health "$MCP_URL" "el servidor MCP"

echo "Todo listo. Abriendo el chat con Llama 3.1."
echo "Logs:"
echo "  API -> $API_LOG"
echo "  MCP -> $MCP_LOG"
echo

exec "$VENV_PY" "$ROOT_DIR/chat_terminal.py"

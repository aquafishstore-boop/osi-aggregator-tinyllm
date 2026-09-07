#!/usr/bin/env bash
# Per-boot reconciliation: ensure the local Ollama runtime is serving.
# Idempotent and non-blocking; the app degrades gracefully if the LLM is down.
set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_HOST

OLLAMA_URL="${OLLAMA_HOST}"
case "$OLLAMA_URL" in
  http://*|https://*) ;;
  *) OLLAMA_URL="http://${OLLAMA_URL}" ;;
esac

if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  echo "ollama already serving on ${OLLAMA_HOST}"
  exit 0
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "WARNING: ollama is not installed; skipping startup" >&2
  exit 0
fi

echo "starting ollama serve on ${OLLAMA_HOST}"
nohup ollama serve >/tmp/ollama-serve.log 2>&1 &

for _ in $(seq 1 60); do
  if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    echo "ollama ready"
    exit 0
  fi
  sleep 1
done

echo "WARNING: ollama did not become ready within 60s (see /tmp/ollama-serve.log)" >&2
exit 0

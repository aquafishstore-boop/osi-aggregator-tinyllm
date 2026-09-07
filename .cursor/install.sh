#!/usr/bin/env bash
# Idempotent bootstrap for the osi-aggregator-tinyllm dev environment.
# Runs after the repository is checked out. Safe to run repeatedly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_HOST

echo "==> System packages"
sudo apt-get update -qq
# python3-venv: ensurepip for venv creation. zstd: required by the Ollama installer.
sudo apt-get install -y -qq python3-venv zstd curl ca-certificates

echo "==> Python virtualenv + dependencies"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
python -m pip install --quiet -e .

echo "==> Local .env (native run parity; explicit terminal env still wins)"
if [ ! -f .env ]; then
  cp .env.example .env
  # Native (non-Docker) runs need an explicit prompts dir and an absolute data dir.
  sed -i "s#^DATA_DIR=.*#DATA_DIR=${REPO_ROOT}/data#" .env
  printf '\n# Native/local runs resolve prompts here (Docker uses /app/prompts)\nPROMPTS_DIR=%s/prompts\n' "$REPO_ROOT" >> .env
fi
mkdir -p "${REPO_ROOT}/data/snapshots" "${REPO_ROOT}/data/reports"

echo "==> Ollama (local tiny-LLM runtime)"
if ! command -v ollama >/dev/null 2>&1; then
  ollama_install_script="$(mktemp)"
  trap 'rm -f "$ollama_install_script"' EXIT
  curl -fsSL https://ollama.com/install.sh -o "$ollama_install_script"
  sh "$ollama_install_script"
fi

echo "==> Pre-pull model ${OLLAMA_MODEL}"
OLLAMA_URL="${OLLAMA_HOST}"
case "$OLLAMA_URL" in
  http://*|https://*) ;;
  *) OLLAMA_URL="http://${OLLAMA_URL}" ;;
esac
if ! curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  nohup ollama serve >/tmp/ollama-install-serve.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1 && break
    sleep 1
  done
fi
ollama pull "${OLLAMA_MODEL}"

echo "==> install.sh complete"

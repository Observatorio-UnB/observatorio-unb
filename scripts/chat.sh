#!/usr/bin/env bash
# Sobe o Ollama do chat usando a GPU se houver (NVIDIA ou AMD), senão CPU.
#   scripts/chat.sh            -> detecta e sobe (ollama + ollama-pull)
#   OLLAMA_URL_REMOTO=https://... scripts/chat.sh   -> cluster remoto (também lida do .env): não sobe nada local
# Ollama nativo no host (OLLAMA_URL=http://localhost:11434) não passa por aqui: ele já usa a GPU sozinho.
set -euo pipefail
cd "$(dirname "$0")/.."

remoto="${OLLAMA_URL_REMOTO:-$(grep -E '^OLLAMA_URL_REMOTO=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || true)}"
if [[ -n "$remoto" ]]; then
  echo "OLLAMA_URL_REMOTO definida (${remoto##*@}): usando servidor remoto, nenhum Ollama local será iniciado."
  exit 0
fi

arquivos=(-f docker-compose.yml)
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  echo "GPU NVIDIA detectada: Ollama usará a GPU."
  arquivos+=(-f docker-compose.gpu-nvidia.yml)
elif [[ -e /dev/kfd && -e /dev/dri ]]; then
  echo "GPU AMD (ROCm) detectada: Ollama usará a GPU."
  arquivos+=(-f docker-compose.gpu-amd.yml)
else
  echo "Nenhuma GPU detectada: Ollama rodará em CPU (a 1ª pergunta leva minutos)."
fi
docker compose "${arquivos[@]}" --profile chat up -d ollama ollama-pull "$@"

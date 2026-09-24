#!/usr/bin/env bash
# Pipeline completo, do portal ao banco: ingestão -> silver -> gold -> auditoria ->
# privacidade -> carga no PostgreSQL -> vetorização -> dicionário do banco.
#
# Requer o banco no ar (docker compose up -d db) ou DATABASE_URL apontando para ele.
# Uso: bash scripts/rodar_pipeline.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if [ -z "${VIRTUAL_ENV:-}" ] && [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
fi

etapa() { echo; echo "=== $1 ==="; }

etapa "Bronze: ingestão via API CKAN"
"$PYTHON" src/ingestion/ckan_client.py

etapa "Silver: limpeza, tipagem e normalização"
"$PYTHON" src/pipeline/transform_silver.py

etapa "Gold: tabela analítica e joins"
"$PYTHON" src/pipeline/build_gold.py

etapa "Auditoria de qualidade"
"$PYTHON" src/audit/quality_auditor.py

etapa "Privacidade: k-anonimato"
"$PYTHON" src/privacy/lgpd_check.py

etapa "Banco: migrações e carga das camadas"
"$PYTHON" src/db/carregar.py

etapa "Busca semântica: vetorização"
"$PYTHON" src/busca/vetorizar.py

etapa "Dicionário de dados do banco"
"$PYTHON" src/db/gerar_dicionario.py

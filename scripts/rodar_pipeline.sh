#!/usr/bin/env bash
# Pipeline completo, do portal ao banco. Cada etapa lê a camada anterior do
# PostgreSQL e grava a sua nele: migrações -> bronze (CKAN e INEP) -> silver -> gold
# -> auditoria -> privacidade -> Silver 3NF e Star Schema -> vetorização -> dicionário do banco.
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

etapa "Banco: migrações do esquema"
"$PYTHON" src/db/migrar.py

etapa "Bronze: ingestão via API CKAN"
"$PYTHON" src/ingestion/ckan_client.py

# O servidor do INEP cai com frequência; sem o arquivo, Silver e Gold pulam o benchmark
# e o painel segue sem o benchmark (mesma regra do CI).
etapa "Bronze: Censo da Educação Superior (INEP)"
"$PYTHON" src/ingestion/inep_censo_superior.py || echo "AVISO: download do INEP falhou; seguindo sem atualizar o benchmark."

# Valor atual da bolsa IC na tabela do CNPq (uma requisição). O JSON de vigências é versionado: se a leitura
# falhar, a Silver usa as vigências já gravadas.
etapa "Bronze: valor da bolsa IC do CNPq"
"$PYTHON" src/ingestion/cnpq_valor_bolsa.py || echo "AVISO: coleta do valor da bolsa falhou; usando as vigências versionadas."

etapa "Silver: limpeza, tipagem e normalização"
"$PYTHON" src/pipeline/transform_silver.py

etapa "Gold: tabela analítica e joins"
"$PYTHON" src/pipeline/build_gold.py

etapa "Auditoria de qualidade"
"$PYTHON" src/audit/quality_auditor.py

etapa "Privacidade: k-anonimato"
"$PYTHON" src/privacy/lgpd_check.py

etapa "Banco: Silver 3NF e Star Schema"
"$PYTHON" src/db/povoar_dimensional.py

etapa "Busca semântica: vetorização"
"$PYTHON" src/busca/vetorizar.py

etapa "Dicionário de dados do banco"
"$PYTHON" src/db/gerar_dicionario.py

# Envia ao Supabase só o que é novo ou mudou na gold e na busca (bronze e silver não saem do
# banco local). Pulada se SUPABASE_DATABASE_URL não estiver definida.
etapa "Supabase: sincronização incremental da gold"
"$PYTHON" src/db/sincronizar_supabase.py

#!/usr/bin/env bash
# Roda o dbt do projeto transform/ contra o banco do DATABASE_URL (o mesmo do pipeline).
#
#   bash scripts/dbt.sh build                  # modelos e testes, na ordem do grafo
#   bash scripts/dbt.sh build --full-refresh   # do zero
#   bash scripts/dbt.sh docs generate          # documentação e linhagem em transform/target/
#
# Requer o dbt instalado: pip install -r requirements-dbt.txt
set -euo pipefail
cd "$(dirname "$0")/.."

DBT="${DBT:-dbt}"
if ! command -v "$DBT" >/dev/null 2>&1 && [ -x .venv/bin/dbt ]; then
  DBT=.venv/bin/dbt
fi

# DATABASE_URL (ou o .env) -> variáveis que transform/profiles.yml lê.
PYTHON="${PYTHON:-python3}"
if [ -z "${VIRTUAL_ENV:-}" ] && [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
fi
eval "$("$PYTHON" - <<'PY'
import shlex, sys
sys.path.insert(0, ".")
from src.db.conexao import variaveis_dbt
for nome, valor in variaveis_dbt().items():
    print(f"export {nome}={shlex.quote(valor)}")
PY
)"

exec "$DBT" "$@" --project-dir transform --profiles-dir transform

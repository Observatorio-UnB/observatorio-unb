#!/usr/bin/env bash
# Conector Debezium da captura de mudanças (Silver 3NF -> Kafka). Requer o profile cdc no ar:
#   docker compose --profile cdc up -d db kafka connect
#
# Uso:
#   bash scripts/cdc.sh registrar   # cria ou atualiza o conector (o slot nasce no primeiro registro)
#   bash scripts/cdc.sh status      # estado do conector e do slot de replicação
#   bash scripts/cdc.sh remover     # apaga o conector E o slot, para o banco não reter WAL
set -euo pipefail
cd "$(dirname "$0")/.."

CONNECT_URL="${CONNECT_URL:-http://localhost:${CONNECT_PORT:-8093}}"
CONECTOR=observatorio-silver
SLOT=observatorio_cdc
PG_USER="${POSTGRES_USER:-observatorio}"
PG_DB="${POSTGRES_DB:-observatorio}"

psql_db() { docker compose exec -T db psql -U "$PG_USER" -d "$PG_DB" -tAc "$1"; }

esperar_connect() {
  for _ in $(seq 60); do
    curl -sf "$CONNECT_URL/connectors" > /dev/null && return 0
    sleep 2
  done
  echo "Kafka Connect não respondeu em $CONNECT_URL." >&2
  exit 1
}

case "${1:-}" in
  registrar)
    esperar_connect
    # JsonConverter sem schema: o consumidor recebe só before/after/op/source.
    # decimal.handling.mode=double: NUMERIC chega como número, e não como bytes em base64.
    # skipped.operations=none: o Debezium ignora TRUNCATE por padrão, e a recarga da Silver faz um.
    # A resposta repete a configuração, senha inclusive: não vai para a saída.
    curl -sf -o /dev/null -X PUT -H "Content-Type: application/json" "$CONNECT_URL/connectors/$CONECTOR/config" -d @- <<JSON
{
  "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
  "plugin.name": "pgoutput",
  "database.hostname": "db",
  "database.port": "5432",
  "database.user": "$PG_USER",
  "database.password": "${POSTGRES_PASSWORD:-observatorio}",
  "database.dbname": "$PG_DB",
  "topic.prefix": "observatorio",
  "table.include.list": "silver.cursos,silver.estruturas_curriculares,silver.movimentacoes_vinculos",
  "publication.name": "observatorio_cdc",
  "publication.autocreate.mode": "disabled",
  "slot.name": "$SLOT",
  "snapshot.mode": "initial",
  "decimal.handling.mode": "double",
  "skipped.operations": "none",
  "tombstones.on.delete": "false",
  "heartbeat.interval.ms": "10000",
  "key.converter": "org.apache.kafka.connect.json.JsonConverter",
  "key.converter.schemas.enable": "false",
  "value.converter": "org.apache.kafka.connect.json.JsonConverter",
  "value.converter.schemas.enable": "false"
}
JSON
    echo "Conector $CONECTOR registrado. Consumir: python3 src/cdc/consumidor.py"
    ;;
  status)
    esperar_connect
    curl -sf "$CONNECT_URL/connectors/$CONECTOR/status" || echo "Conector $CONECTOR não registrado."
    echo
    psql_db "SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_retido
             FROM pg_replication_slots WHERE slot_name = '$SLOT'"
    ;;
  remover)
    curl -sf -X DELETE "$CONNECT_URL/connectors/$CONECTOR" && echo "Conector $CONECTOR removido." || true
    # O slot sobrevive ao conector e segura WAL até ser apagado. Depois de desativado o conector,
    # o walsender leva alguns segundos para soltá-lo.
    for _ in $(seq 15); do
      [ "$(psql_db "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$SLOT' AND active")" = 0 ] && break
      sleep 1
    done
    psql_db "SELECT pg_drop_replication_slot('$SLOT') FROM pg_replication_slots WHERE slot_name = '$SLOT'" > /dev/null
    echo "Slot $SLOT removido."
    ;;
  *)
    echo "Uso: bash scripts/cdc.sh {registrar|status|remover}" >&2
    exit 1
    ;;
esac

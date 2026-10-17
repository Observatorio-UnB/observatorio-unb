#!/usr/bin/env bash
# Conector Debezium da captura de mudanças (Silver 3NF -> Kafka). Requer o profile cdc no ar:
#   docker compose --profile cdc up -d db kafka connect
# e curl e jq no host.
#
# Uso:
#   bash scripts/cdc.sh registrar   # cria ou atualiza o conector (o slot nasce no primeiro registro)
#   bash scripts/cdc.sh status      # estado do conector e do slot de replicação
#   bash scripts/cdc.sh remover     # apaga o conector, os offsets dele E o slot, para o banco não reter WAL
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
    # topic.creation.default.*: tópicos sem retenção por tempo. Com a retenção padrão do Kafka
    # (7 dias), um consumidor parado por mais tempo perderia eventos, e um DELETE perdido deixa a
    # linha viva no lago. Vale para os tópicos que o conector cria: os que já existem ficam como estão.
    # jq monta o JSON: uma senha com aspas ou barra invertida não quebra o documento.
    config=$(jq -n --arg user "$PG_USER" --arg senha "${POSTGRES_PASSWORD:-observatorio}" \
      --arg db "$PG_DB" --arg slot "$SLOT" '{
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "plugin.name": "pgoutput",
        "database.hostname": "db",
        "database.port": "5432",
        "database.user": $user,
        "database.password": $senha,
        "database.dbname": $db,
        "topic.prefix": "observatorio",
        "table.include.list": "silver.cursos,silver.estruturas_curriculares,silver.movimentacoes_vinculos",
        "publication.name": "observatorio_cdc",
        "publication.autocreate.mode": "disabled",
        "slot.name": $slot,
        "snapshot.mode": "initial",
        "decimal.handling.mode": "double",
        "skipped.operations": "none",
        "tombstones.on.delete": "false",
        "heartbeat.interval.ms": "10000",
        "topic.creation.default.replication.factor": "1",
        "topic.creation.default.partitions": "1",
        "topic.creation.default.retention.ms": "-1",
        "key.converter": "org.apache.kafka.connect.json.JsonConverter",
        "key.converter.schemas.enable": "false",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter.schemas.enable": "false"
      }')
    # A resposta de sucesso repete a configuração, senha inclusive: só o erro vai para a saída.
    resposta=$(mktemp)
    trap 'rm -f "$resposta"' EXIT
    codigo=$(curl -s -o "$resposta" -w '%{http_code}' -X PUT -H "Content-Type: application/json" \
      "$CONNECT_URL/connectors/$CONECTOR/config" -d "$config")
    if [ "${codigo:0:1}" != 2 ]; then
      echo "Falha ao registrar o conector $CONECTOR (HTTP $codigo):" >&2
      jq -r '.message // .' "$resposta" >&2 2>/dev/null || cat "$resposta" >&2
      exit 1
    fi
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
    # Parar, apagar os offsets e só então o conector: sem os offsets, o próximo registrar refaz o
    # snapshot inicial em vez de retomar de uma posição que o slot novo já não tem.
    if curl -sf -X PUT "$CONNECT_URL/connectors/$CONECTOR/stop" > /dev/null; then
      for _ in $(seq 15); do
        curl -sf "$CONNECT_URL/connectors/$CONECTOR/status" | grep -q '"STOPPED"' && break
        sleep 1
      done
      curl -sf -X DELETE "$CONNECT_URL/connectors/$CONECTOR/offsets" > /dev/null \
        || echo "Aviso: os offsets do conector não foram apagados; o próximo registrar não refaz o snapshot." >&2
      curl -sf -X DELETE "$CONNECT_URL/connectors/$CONECTOR" > /dev/null
      echo "Conector $CONECTOR removido."
    else
      echo "Conector $CONECTOR não registrado (ou Kafka Connect fora do ar)."
    fi
    # O slot sobrevive ao conector e segura WAL até ser apagado. Depois de desativado o conector,
    # o walsender leva alguns segundos para soltá-lo.
    if [ "$(psql_db "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$SLOT'")" = 0 ]; then
      echo "Slot $SLOT não existe."
      exit 0
    fi
    for _ in $(seq 15); do
      [ "$(psql_db "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$SLOT' AND active")" = 0 ] && break
      sleep 1
    done
    if [ "$(psql_db "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$SLOT' AND active")" != 0 ]; then
      echo "Slot $SLOT ainda em uso depois de 15 s (o conector parou?). Tente de novo ou veja: bash scripts/cdc.sh status" >&2
      exit 1
    fi
    psql_db "SELECT pg_drop_replication_slot('$SLOT')" > /dev/null
    echo "Slot $SLOT removido."
    ;;
  *)
    echo "Uso: bash scripts/cdc.sh {registrar|status|remover}" >&2
    exit 1
    ;;
esac

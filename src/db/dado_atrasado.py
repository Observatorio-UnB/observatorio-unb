"""
Dado atrasado na Silver 3NF: o retrato de cada carga e o que chegou depois do prazo.

O tempo de evento de um vínculo é o período da saída; o tempo de processamento é a publicação
do arquivo no portal. Uma saída só entra no arquivo quando é registrada (a formatura, com o
registro do diploma), então um período continua recebendo vínculos depois de terminar. A marca
d'água de uma carga é o último período cujo fim, somado à TOLERANCIA_MESES, não passa da
publicação: até ela, o período é dado como fechado.

Cada carga da Silver 3NF (src/db/povoar_silver_3nf.py) chama registrar_carga, que grava em
silver.cargas_vinculos a marca d'água e em silver.cargas_vinculos_retrato quantos vínculos há
por ano de ingresso, desfecho e período de saída. A view silver.chegadas_por_carga (migração
0021) compara o retrato com o da carga anterior e classifica cada diferença:

- ATRASADA: período até a marca d'água da carga anterior, que já o dava como fechado;
- NO_PRAZO: período depois dessa marca, ainda aberto na carga anterior;
- SEM_PERIODO: vínculo sem período de saída (ativo, cancelado no SIGAA, formado sem diploma).

O dado atrasado não é descartado. A fonte é a referência, então a carga o aceita e a gold é
recalculada. A chegada atrasada fica registrada, com aviso quando revisa uma coorte que a gold
já publicava. No lago, a janela que a recebeu é reprocessada (exportar_lago.py
--janelas-alteradas). Decisão no ADR 0026.

Uso:
    python3 src/db/dado_atrasado.py              # o que chegou na última carga, por quinquênio
    python3 src/db/dado_atrasado.py --carga 3    # numa carga específica
    python3 src/db/dado_atrasado.py --medir      # atraso do registro do diploma no SIGRA
"""

import argparse
import calendar
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.ingestion.ckan_client import DATASETS_CONFIG  # noqa: E402
from src.pipeline.build_gold import ANOS_MATURACAO_COORTE  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dado_atrasado")

# No SIGRA, 99% dos diplomas foram registrados até 105 dias depois do fim do semestre de
# conclusão, e 0,8% passaram de 4 meses (--medir). É também a janela da regra que estima o
# semestre no SIGAA (ADR 0015): o 2º semestre recebe registros até abril.
TOLERANCIA_MESES = 4

FONTES_DOS_VINCULOS = tuple(DATASETS_CONFIG[chave]["tabela"] for chave in ("sigra", "sigaa"))


def rotulo(periodo: int) -> str:
    """20232 -> '2023/2'."""
    return f"{periodo // 10}/{periodo % 10}"


def fim_do_periodo(periodo: int) -> date:
    """Fim nominal do período AAAAS: verão (0) em fevereiro, 1º semestre em julho, 2º em dezembro."""
    ano, semestre = divmod(periodo, 10)
    if semestre == 0:
        return date(ano, 3, 1) - timedelta(days=1)
    return date(ano, 7, 31) if semestre == 1 else date(ano, 12, 31)


def _menos_meses(data: date, meses: int) -> date:
    ano, mes = divmod(data.year * 12 + data.month - 1 - meses, 12)
    return date(ano, mes + 1, min(data.day, calendar.monthrange(ano, mes + 1)[1]))


def marca_dagua(publicada_em: date, tolerancia_meses: int = TOLERANCIA_MESES) -> int:
    """Último período AAAAS cujo fim, somado à tolerância, não passa da publicação."""
    limite = _menos_meses(publicada_em, tolerancia_meses)
    for ano in (limite.year, limite.year - 1):
        for semestre in (2, 1, 0):
            if fim_do_periodo(ano * 10 + semestre) <= limite:
                return ano * 10 + semestre
    raise AssertionError("o 2º semestre do ano anterior sempre termina antes do limite")


# Data do recurso baixado, como o portal a informa (o mesmo recurso de bronze.ingestoes.recurso_url).
# Sem os metadados do CKAN, vale a data do download.
SQL_PUBLICACAO = """
SELECT coalesce(max(coalesce(r->>'last_modified', r->>'created')::date), max(i.baixado_em)::date)
FROM bronze.ingestoes i
LEFT JOIN LATERAL jsonb_array_elements(i.metadados->'resources') r ON r->>'url' = i.recurso_url
WHERE i.tabela = ANY(%s)
"""

SQL_CARGA = """
INSERT INTO silver.cargas_vinculos (publicada_em, marca_dagua, ultima_coorte_madura, total_vinculos)
SELECT %(publicada_em)s, %(marca_dagua)s, max(ano_ingresso) - %(anos_maturacao)s, count(*)
FROM silver.movimentacoes_vinculos
RETURNING id_carga
"""

SQL_RETRATO = """
INSERT INTO silver.cargas_vinculos_retrato (id_carga, ano_ingresso, tipo_saida_grupo, periodo_saida, total)
SELECT %(id_carga)s, ano_ingresso, tipo_saida_grupo, ano_saida * 10 + semestre_saida, count(*)
FROM silver.movimentacoes_vinculos
GROUP BY ano_ingresso, tipo_saida_grupo, ano_saida * 10 + semestre_saida
"""

SQL_RESUMO = """
SELECT quinquenio_ingresso, chegada,
       coalesce(sum(diferenca) FILTER (WHERE diferenca > 0), 0)::int AS a_mais,
       coalesce(-sum(diferenca) FILTER (WHERE diferenca < 0), 0)::int AS a_menos,
       count(DISTINCT ano_ingresso) FILTER (WHERE coorte_publicada)::int AS coortes_publicadas
FROM silver.chegadas_por_carga
WHERE id_carga = %s
GROUP BY quinquenio_ingresso, chegada
ORDER BY quinquenio_ingresso, chegada
"""

# Atraso do registro do diploma em relação ao fim nominal do semestre de conclusão, no SIGRA,
# que publica as duas datas (o SIGAA só publica o registro). Mesmo fim de fim_do_periodo.
SQL_ATRASO_REGISTRO = """
WITH formados AS (
    SELECT data_registro_diploma - CASE semestre_saida WHEN 0 THEN make_date(ano_saida, 3, 1) - 1
                                                       WHEN 1 THEN make_date(ano_saida, 7, 31)
                                                       ELSE make_date(ano_saida, 12, 31) END AS dias
    FROM silver.discentes_graduacao
    WHERE fonte = 'SIGRA' AND tipo_saida_grupo = 'FORMATURA'
      AND data_registro_diploma IS NOT NULL AND ano_saida IS NOT NULL
)
SELECT count(*),
       percentile_cont(ARRAY[0.5, 0.9, 0.95, 0.99]) WITHIN GROUP (ORDER BY dias),
       100.0 * avg((dias > %(dias_tolerancia)s)::int)
FROM formados
"""


def publicacao_dos_vinculos(conn: psycopg.Connection) -> Optional[date]:
    """Publicação, no portal, do arquivo de vínculos mais recente baixado (SIGRA ou SIGAA)."""
    return conn.execute(SQL_PUBLICACAO, (list(FONTES_DOS_VINCULOS),)).fetchone()[0]


def resumo(conn: psycopg.Connection, id_carga: int) -> List[Tuple[int, str, int, int, int]]:
    """(quinquênio, chegada, vínculos a mais, a menos, coortes publicadas revisadas) da carga."""
    return conn.execute(SQL_RESUMO, (id_carga,)).fetchall()


def registrar_carga(conn: psycopg.Connection, publicada_em: Optional[date] = None) -> int:
    """Grava a marca d'água e o retrato da carga atual de silver.movimentacoes_vinculos.

    Roda na transação da carga (povoar_silver_3nf): se a carga for desfeita, o registro também é.
    Devolve o id da carga.
    """
    publicada_em = publicada_em or publicacao_dos_vinculos(conn) or date.today()
    marca = marca_dagua(publicada_em)
    id_carga = conn.execute(SQL_CARGA, {
        "publicada_em": publicada_em, "marca_dagua": marca, "anos_maturacao": ANOS_MATURACAO_COORTE,
    }).fetchone()[0]
    conn.execute(SQL_RETRATO, {"id_carga": id_carga})
    _registrar_no_log(conn, id_carga, publicada_em, marca)
    return id_carga


def _registrar_no_log(conn: psycopg.Connection, id_carga: int, publicada_em: date, marca: int) -> None:
    logger.info(f"Carga {id_carga}: publicação de {publicada_em:%d/%m/%Y}, marca d'água {rotulo(marca)}.")
    if conn.execute("SELECT count(*) FROM silver.cargas_vinculos WHERE id_carga < %s", (id_carga,)).fetchone()[0] == 0:
        logger.info("Primeira carga registrada: não há retrato anterior para comparar.")
        return
    linhas = resumo(conn, id_carga)
    if not linhas:
        logger.info("Nenhuma janela mudou desde a carga anterior.")
    for quinquenio, chegada, a_mais, a_menos, coortes in linhas:
        mensagem = f"Quinquênio {quinquenio}, {chegada}: +{a_mais:,} / -{a_menos:,} vínculos"
        if chegada == "ATRASADA" and coortes:
            logger.warning(f"{mensagem}; revisa {coortes} coorte(s) já publicada(s) na gold.")
        else:
            logger.info(f"{mensagem}.")


def medir_atraso_do_registro(conn: psycopg.Connection, tolerancia_meses: int = TOLERANCIA_MESES) -> dict:
    """Quantis do atraso do registro do diploma no SIGRA e a parcela que passa da tolerância."""
    total, quantis, acima = conn.execute(
        SQL_ATRASO_REGISTRO, {"dias_tolerancia": round(tolerancia_meses * 365.25 / 12)}
    ).fetchone()
    if not total:
        return {"formados": 0}
    p50, p90, p95, p99 = quantis
    return {"formados": total, "p50": p50, "p90": p90, "p95": p95, "p99": p99, "pct_acima": float(acima)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--carga", type=int, help="Carga a mostrar (padrão: a última).")
    parser.add_argument("--medir", action="store_true",
                        help="Mede o atraso do registro do diploma no SIGRA, base da tolerância.")
    args = parser.parse_args()

    with conectar() as conn:
        if args.medir:
            m = medir_atraso_do_registro(conn)
            if not m["formados"]:
                print("Sem formados do SIGRA na silver. Rode o pipeline antes.")
                return
            print(f"Formados do SIGRA com período e data de registro do diploma: {m['formados']:,}")
            print("Dias do fim do semestre de conclusão até o registro: "
                  f"mediana {m['p50']:.0f}, p90 {m['p90']:.0f}, p95 {m['p95']:.0f}, p99 {m['p99']:.0f}")
            print(f"Registrados mais de {TOLERANCIA_MESES} meses depois do fim: {m['pct_acima']:.1f}%")
            return

        carga = conn.execute(
            "SELECT id_carga, publicada_em, marca_dagua, total_vinculos FROM silver.cargas_vinculos "
            "WHERE id_carga = coalesce(%s, (SELECT max(id_carga) FROM silver.cargas_vinculos))",
            (args.carga,),
        ).fetchone()
        if carga is None:
            print("Nenhuma carga registrada. Rode src/db/povoar_dimensional.py.")
            return
        id_carga, publicada_em, marca, total = carga
        print(f"Carga {id_carga}: {total:,} vínculos, publicação de {publicada_em:%d/%m/%Y}, "
              f"marca d'água {rotulo(marca)} (tolerância de {TOLERANCIA_MESES} meses)\n")
        linhas = resumo(conn, id_carga)
        if not linhas:
            print("Nada mudou em relação à carga anterior (ou é a primeira carga).")
            return
        print(f"{'quinquênio':<12}{'chegada':<13}{'a mais':>8}{'a menos':>9}{'coortes publicadas':>20}")
        for quinquenio, chegada, a_mais, a_menos, coortes in linhas:
            print(f"{quinquenio:<12}{chegada:<13}{a_mais:>8,}{a_menos:>9,}{coortes:>20}")


if __name__ == "__main__":
    main()

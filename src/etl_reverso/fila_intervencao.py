"""
ETL reverso: leva os cursos em RETENÇÃO CRÍTICA para a fila de intervenção (operacional.fila_intervencao).

Quem consome: a coordenação de cada curso, acompanhada pelo Decanato de Ensino de Graduação (DEG). O
que faz com o dado: abre a linha do seu curso, registra o responsável e o plano de ação, e avança o
status (NOVO -> EM_ANALISE -> PLANO_EM_EXECUCAO -> CONCLUIDO). O DEG acompanha quais cursos críticos
ainda estão sem plano e se os que tiveram plano saíram da fila nos ciclos seguintes.

Origem: dbt_marts.painel_cursos_criticos, a mesma tabela de onde o painel tira o ranking. O número que
a coordenação vê na fila é o mesmo do painel, calculado pelas mesmas macros da camada semântica
(transform/macros/metricas.sql), e cada linha leva a versão da definição de cada métrica
(dbt_marts.metricas_definicoes). Nenhuma fórmula é refeita aqui.

Como empurra (push, depois de cada carga mensal, no pipeline e no Dagster):
  - por estado, e não por evento: cada execução leva o destino ao estado da origem. Rodar duas vezes
    não muda nada (só grava linha cujo valor mudou), e uma execução perdida é coberta pela seguinte;
  - numa transação: o destino nunca fica com metade de um ciclo;
  - sem sobrescrever o que a coordenação escreveu (status, responsável, plano de ação);
  - curso que sai da RETENÇÃO CRÍTICA fica na tabela com na_fila = false e a data de saída;
  - recusa um ciclo mais antigo que o do destino (export de um banco desatualizado não desfaz o mais
    novo) e recusa origem vazia (dbt não rodou), em vez de tirar todo mundo da fila.

Destino fora do ar: 4 tentativas com espera crescente (2, 4 e 8 s). Esgotadas, sai com código 2 e o
Dagster aplica a política de retry do asset. Como a sincronização é por estado, a próxima execução
que conseguir conectar leva o destino ao estado atual, sem fila de eventos pendentes.

Destino: ETL_REVERSO_DATABASE_URL (ambiente ou .env). Sem ela, o próprio banco da plataforma.

Uso:
    python3 src/etl_reverso/fila_intervencao.py                    # sincroniza o destino
    python3 src/etl_reverso/fila_intervencao.py --preparar-destino # cria a tabela num destino novo
    python3 src/etl_reverso/fila_intervencao.py --csv export/fila_intervencao.csv
                                                     # a opção nula: o mesmo conteúdo num CSV
"""

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, TypeVar

import psycopg
from psycopg.rows import dict_row

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar, database_url, ler_variavel  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("etl_reverso")

MIGRACAO_DESTINO = BASE_DIR / "db" / "migrations" / "0027_fila_intervencao.sql"
CLASSIFICACAO_DA_FILA = "RETENÇÃO CRÍTICA"
ESPERAS_S = (2, 4, 8)

# Colunas que o ETL reverso escreve. As de andamento (status, responsavel, plano_de_acao) ficam de fora.
COLUNAS_METRICA = (
    "campus", "area_conhecimento", "posicao", "classificacao_retencao", "indice_retencao_critica",
    "taxa_evasao_pct", "atraso_medio_semestres", "formados_tempo_ideal_pct", "total_ingressantes",
)
# Métricas cuja definição vai junto, em versao_metricas.
METRICAS_GRAVADAS = (
    "indice_retencao_critica", "classificacao_retencao", "taxa_evasao_pct", "atraso_medio_semestres",
    "formados_tempo_ideal_pct", "ingressantes",
)

SQL_ORIGEM = f"""
    SELECT nome_curso, {", ".join(COLUNAS_METRICA)}
    FROM dbt_marts.painel_cursos_criticos
    WHERE classificacao_retencao = %s
    ORDER BY posicao, nome_curso
"""


class OrigemInvalida(RuntimeError):
    """A origem não serve para sincronizar: vazia, ou mais antiga que o destino."""


@dataclass
class Resultado:
    cursos_na_origem: int
    inseridos: int
    atualizados: int
    sairam_da_fila: int
    duracao_ms: int


T = TypeVar("T")


def com_retentativas(operacao: Callable[[], T], esperas: Sequence[float] = ESPERAS_S,
                     dormir: Callable[[float], None] = time.sleep) -> T:
    """Roda `operacao`, repetindo nas falhas de conexão com o destino. A última falha sobe."""
    for tentativa, espera in enumerate([*esperas, None], start=1):
        try:
            return operacao()
        except psycopg.OperationalError as erro:
            if espera is None:
                raise
            logger.warning(f"Destino indisponível (tentativa {tentativa}): {erro}. Nova tentativa em {espera} s.")
            dormir(espera)
    raise AssertionError("inalcançável")


def versao_metricas(definicoes: Dict[str, str]) -> str:
    """'metrica@versao;...' das métricas gravadas na fila. Métrica sem definição é erro."""
    faltando = [m for m in METRICAS_GRAVADAS if m not in definicoes]
    if faltando:
        raise OrigemInvalida(f"Métricas sem definição em dbt_marts.metricas_definicoes: {faltando}")
    return ";".join(f"{m}@{definicoes[m]}" for m in METRICAS_GRAVADAS)


def ler_origem(conn: psycopg.Connection) -> tuple:
    """(cursos em RETENÇÃO CRÍTICA, versão das métricas, ciclo dos dados) da origem."""
    with conn.cursor(row_factory=dict_row) as cur:
        cursos = cur.execute(SQL_ORIGEM, (CLASSIFICACAO_DA_FILA,)).fetchall()
        definicoes = {r["metrica"]: r["versao"] for r in
                      cur.execute("SELECT metrica, versao FROM dbt_marts.metricas_definicoes").fetchall()}
        ciclo = cur.execute("SELECT max(_carregado_em) AS ciclo FROM gold.relatorios").fetchone()["ciclo"]
    if not cursos:
        raise OrigemInvalida("Nenhum curso em RETENÇÃO CRÍTICA na origem: o dbt rodou? Destino não alterado.")
    if ciclo is None:
        raise OrigemInvalida("gold.relatorios sem carga: sem ciclo de dados para gravar. Destino não alterado.")
    return cursos, versao_metricas(definicoes), ciclo


def sincronizar(destino: psycopg.Connection, cursos: List[Dict], versao: str, ciclo: datetime) -> Resultado:
    """Leva a fila do destino ao estado da origem, numa transação. Devolve o que mudou."""
    inicio = time.monotonic()
    with destino.transaction(), destino.cursor() as cur:
        # Serializa execuções concorrentes do ETL reverso no mesmo destino.
        cur.execute("LOCK TABLE operacional.fila_intervencao IN SHARE ROW EXCLUSIVE MODE")
        ciclo_destino = cur.execute(
            "SELECT max(ciclo_dados) FROM operacional.fila_intervencao_execucoes").fetchone()[0]
        if ciclo_destino is not None and ciclo < ciclo_destino:
            raise OrigemInvalida(f"Ciclo da origem ({ciclo}) mais antigo que o do destino ({ciclo_destino}). "
                                 "Destino não alterado.")

        colunas = ("nome_curso", *COLUNAS_METRICA)
        # Recriada a cada chamada: duas sincronizações na mesma transação (os testes) não se misturam.
        cur.execute("DROP TABLE IF EXISTS pg_temp.origem")
        cur.execute(f"""CREATE TEMP TABLE origem ON COMMIT DROP AS
                        SELECT {', '.join(colunas)} FROM operacional.fila_intervencao WITH NO DATA""")
        with cur.copy(f"COPY origem ({', '.join(colunas)}) FROM STDIN") as copia:
            for curso in cursos:
                copia.write_row([curso[c] for c in colunas])

        lista = ", ".join(COLUNAS_METRICA)
        atribuicoes = ", ".join(f"{c} = excluded.{c}" for c in COLUNAS_METRICA)
        mudou = " OR ".join(f"f.{c} IS DISTINCT FROM excluded.{c}" for c in COLUNAS_METRICA)
        # Novo na fila, de volta a ela, ou com métrica diferente: grava. Só toca a linha que mudou de
        # fato, para a reexecução de um mesmo ciclo não alterar nada. O andamento não é tocado.
        cur.execute(f"""
            WITH gravados AS (
                INSERT INTO operacional.fila_intervencao AS f
                    (nome_curso, {lista}, versao_metricas, ciclo_dados, na_fila, entrou_na_fila_em)
                SELECT nome_curso, {lista}, %(versao)s, %(ciclo)s, true, current_date FROM origem
                ON CONFLICT (nome_curso) DO UPDATE SET
                    {atribuicoes},
                    versao_metricas = excluded.versao_metricas,
                    ciclo_dados = excluded.ciclo_dados,
                    entrou_na_fila_em = CASE WHEN f.na_fila THEN f.entrou_na_fila_em ELSE current_date END,
                    na_fila = true,
                    saiu_da_fila_em = NULL,
                    sincronizado_em = now()
                WHERE NOT f.na_fila
                   OR f.versao_metricas IS DISTINCT FROM excluded.versao_metricas
                   OR {mudou}
                RETURNING (xmax = 0) AS inserido
            )
            SELECT count(*) FILTER (WHERE inserido), count(*) FILTER (WHERE NOT inserido) FROM gravados
        """, {"versao": versao, "ciclo": ciclo})
        inseridos, atualizados = cur.fetchone()

        cur.execute("""
            UPDATE operacional.fila_intervencao f
            SET na_fila = false, saiu_da_fila_em = current_date, sincronizado_em = now(), ciclo_dados = %s
            WHERE f.na_fila AND NOT EXISTS (SELECT 1 FROM origem o WHERE o.nome_curso = f.nome_curso)
        """, (ciclo,))
        sairam = cur.rowcount

        duracao_ms = int((time.monotonic() - inicio) * 1000)
        cur.execute("""
            INSERT INTO operacional.fila_intervencao_execucoes
                (ciclo_dados, cursos_na_origem, inseridos, atualizados, sairam_da_fila, duracao_ms)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (ciclo, len(cursos), inseridos, atualizados, sairam, duracao_ms))
    return Resultado(len(cursos), inseridos, atualizados, sairam, duracao_ms)


def gravar_csv(cursos: List[Dict], versao: str, ciclo: datetime, caminho: Path) -> Path:
    """A opção nula: o mesmo conteúdo da fila num arquivo, sem destino, sem andamento, sem histórico."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["nome_curso", *COLUNAS_METRICA, "versao_metricas", "ciclo_dados"])
        for curso in cursos:
            escritor.writerow([curso["nome_curso"], *(curso[c] for c in COLUNAS_METRICA), versao, ciclo.isoformat()])
    return caminho


def url_destino() -> str:
    return ler_variavel("ETL_REVERSO_DATABASE_URL") or database_url()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--preparar-destino", action="store_true",
                        help="Aplica db/migrations/0027_fila_intervencao.sql no destino (idempotente).")
    parser.add_argument("--csv", type=Path, help="Grava a fila neste CSV em vez de sincronizar o destino.")
    args = parser.parse_args(argv)

    try:
        with conectar() as origem:
            cursos, versao, ciclo = ler_origem(origem)
    except OrigemInvalida as erro:
        logger.error(str(erro))
        return 1
    logger.info(f"Origem: {len(cursos)} cursos em {CLASSIFICACAO_DA_FILA}, ciclo {ciclo:%Y-%m-%d %H:%M}, {versao}.")

    if args.csv:
        logger.info(f"Fila gravada em {gravar_csv(cursos, versao, ciclo, args.csv)}.")
        return 0

    def executar() -> Resultado:
        with conectar(url_destino(), connect_timeout=10) as destino:
            if args.preparar_destino:
                destino.execute(MIGRACAO_DESTINO.read_text(encoding="utf-8"))
                destino.commit()
            return sincronizar(destino, cursos, versao, ciclo)

    try:
        resultado = com_retentativas(executar)
    except OrigemInvalida as erro:
        logger.error(str(erro))
        return 1
    except psycopg.OperationalError as erro:
        logger.error(f"Destino fora do ar depois de {len(ESPERAS_S) + 1} tentativas: {erro}. "
                     "Nada foi gravado; a próxima execução leva o destino ao estado atual.")
        return 2
    logger.info(f"Fila de intervenção sincronizada em {resultado.duracao_ms} ms: {resultado.inseridos} novos, "
                f"{resultado.atualizados} atualizados, {resultado.sairam_da_fila} saíram da fila.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

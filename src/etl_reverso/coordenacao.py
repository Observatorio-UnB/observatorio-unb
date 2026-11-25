"""
O lado de quem age: a coordenação lê a fila de intervenção e registra o andamento.

É a aplicação que consome o ETL reverso (src/etl_reverso/fila_intervencao.py). O painel a usa na tela
"Fila de Intervenção" quando está ligado ao banco; sem banco (GitHub Pages), a tela explica onde a fila
vive. Lê e grava no banco da fila (url_fila_intervencao: ETL_REVERSO_DATABASE_URL ou o da plataforma),
o mesmo em que o ETL reverso grava.

Privilégio por coluna (migração 0029): o papel coordenacao_academica só grava status, responsável e
plano de ação. Quem garante isso depende de como se conecta:
  - com um login próprio da coordenação (CREATE ROLE ... LOGIN IN ROLE coordenacao_academica, sem ser
    dono das tabelas), o banco garante: não há como gravar uma métrica nem apagar uma linha;
  - pela conexão do dono (o painel local e esta linha de comando, no ambiente do projeto), este módulo
    troca para o papel com SET LOCAL ROLE antes de cada operação. O banco recusa o que o papel não pode
    fazer, mas a troca é decisão do código: quem tem a conexão do dono pode simplesmente não trocar.
Em produção, cada coordenação teria o próprio login, e a conexão do dono ficaria só com o pipeline.

Uso, sem o painel:
    python3 src/etl_reverso/coordenacao.py                                  # a fila, do mais crítico
    python3 src/etl_reverso/coordenacao.py --curso COMPUTACAO --status EM_ANALISE --responsavel coord.cic
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd
import psycopg
from psycopg.rows import dict_row

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar, url_fila_intervencao  # noqa: E402

PAPEL = "coordenacao_academica"
STATUS = ("NOVO", "EM_ANALISE", "PLANO_EM_EXECUCAO", "CONCLUIDO", "DESCARTADO")

SQL_FILA = """
    SELECT posicao, nome_curso, campus, status, responsavel, plano_de_acao, indice_retencao_critica,
           taxa_evasao_pct, atraso_medio_semestres, total_ingressantes, entrou_na_fila_em,
           saiu_da_fila_em, na_fila, versao_metricas, atualizado_pela_coordenacao_em
    FROM operacional.fila_intervencao
    ORDER BY na_fila DESC, posicao NULLS LAST, nome_curso
"""


def ler_fila(conn: psycopg.Connection) -> pd.DataFrame:
    """A fila como o papel da coordenação a vê."""
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SET LOCAL ROLE {PAPEL}")
        fila = pd.DataFrame(cur.execute(SQL_FILA).fetchall())
        # Dentro de um savepoint, SET LOCAL sobrevive ao release e vazaria para o resto da transação
        # de quem chamou. Volta ao papel da sessão; numa falha, o rollback já o desfaz.
        cur.execute("RESET ROLE")
    return fila


def registrar_andamento(conn: psycopg.Connection, nome_curso: str, status: str,
                        responsavel: Optional[str], plano_de_acao: Optional[str]) -> None:
    """Grava o andamento de um curso como coordenacao_academica. Status fora da lista é recusado."""
    if status not in STATUS:
        raise ValueError(f"Status inválido: {status}. Use um de {STATUS}.")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(f"SET LOCAL ROLE {PAPEL}")
        cur.execute("""
            UPDATE operacional.fila_intervencao
            SET status = %s, responsavel = nullif(%s, ''), plano_de_acao = nullif(%s, ''),
                atualizado_pela_coordenacao_em = now()
            WHERE nome_curso = %s
        """, (status, responsavel, plano_de_acao, nome_curso))
        if cur.rowcount != 1:
            raise LookupError(f"Curso fora da fila de intervenção: {nome_curso}")
        cur.execute("RESET ROLE")


def alteracoes(antes: pd.DataFrame, depois: pd.DataFrame) -> List[dict]:
    """Linhas cujo andamento (status, responsável, plano) a tela alterou."""
    campos = ["status", "responsavel", "plano_de_acao"]
    a = antes.set_index("nome_curso")[campos].fillna("")
    d = depois.set_index("nome_curso")[campos].fillna("")
    mudou = (a != d.reindex(a.index)).any(axis=1)
    return [{"nome_curso": nome, **d.loc[nome].to_dict()} for nome in a.index[mudou]]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--curso")
    parser.add_argument("--status", choices=STATUS)
    parser.add_argument("--responsavel")
    parser.add_argument("--plano")
    args = parser.parse_args(argv)
    with conectar(url_fila_intervencao()) as conn:
        if args.curso:
            registrar_andamento(conn, args.curso, args.status or "EM_ANALISE", args.responsavel, args.plano)
            print(f"Andamento de {args.curso} registrado.")
        fila = ler_fila(conn)
    pendentes = fila[fila["na_fila"] & (fila["status"] == "NOVO")]
    print(f"{int(fila['na_fila'].sum())} cursos na fila, {len(pendentes)} sem andamento (NOVO).")
    print(fila[["posicao", "nome_curso", "status", "responsavel", "taxa_evasao_pct"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

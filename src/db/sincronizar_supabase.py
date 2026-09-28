"""
Sincroniza a gold e a busca semântica do banco local com o Supabase, de forma incremental.

Só vão as tabelas agregadas (gold, k >= 5) e busca.documentos: bronze e silver têm dado pessoal
e não saem do banco local (docs/registro_privacidade_lgpd.md).

Cada tabela é comparada pela chave natural:
  - linha que não existe no Supabase é inserida;
  - linha que existe e mudou é atualizada (com --somente-inserir, fica como está);
  - linha igual não é reescrita, e nada é apagado no Supabase.
Rodar duas vezes seguidas não duplica nem altera nada.

As chaves substitutas do Star Schema (sk_curso, sk_campus) são de cada banco: os fatos viajam
com o nome do curso e do campus e são religados às dimensões do Supabase na chegada.

O destino vem de SUPABASE_DATABASE_URL (ambiente ou .env). Sem ela, a etapa é pulada.
As migrações pendentes são aplicadas no destino antes da cópia.

Uso:
    python3 src/db/sincronizar_supabase.py [--somente-inserir]
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar, database_url, ler_variavel  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sincronizar_supabase")

# Carimbos de data preenchidos pelo próprio banco: não entram na comparação e são renovados
# quando a linha muda.
CARIMBOS = {"atualizado_em", "_carregado_em"}


@dataclass
class Sincronia:
    tabela: str
    chave: List[str]
    # SELECT que exporta as linhas; roda na origem e define a tabela temporária no destino.
    # Sem ele, exporta as colunas da própria tabela (menos identidade e carimbos).
    exportar: Optional[str] = None
    # SELECT sobre `tmp` que produz as colunas de `tabela` na ordem de `colunas`, no destino.
    inserir: Optional[str] = None
    colunas: Optional[List[str]] = None
    # Alvo do ON CONFLICT quando a chave única é uma constraint nomeada.
    conflito: Optional[str] = None


MEDIDAS_RETENCAO = [
    "total_ingressantes", "total_formados", "total_evadidos", "total_ainda_ativos", "taxa_formatura_pct",
    "taxa_evasao_pct", "formados_tempo_ideal_pct", "atraso_medio_semestres", "indice_retencao_critica",
    "classificacao_retencao",
]
MEDIDAS_ATIVOS = [
    "sk_tempo_referencia", "total_ativos", "ativos_acima_prazo_ideal", "ativos_acima_prazo_maximo",
    "pct_acima_prazo_ideal",
]

# Ordem importa: dimensões antes dos fatos.
SINCRONIAS = [
    Sincronia("gold.retencao_cursos_unb", ["curso"]),
    Sincronia("gold.ativos_hoje_cursos_unb", ["curso"]),
    Sincronia("gold.pibic_social_unb", ["curso_pibic_norm", "campus"]),
    Sincronia("gold.regras_harmonizacao_canonicas", ["origem_sigra"]),
    Sincronia("gold.relatorios", ["nome"]),
    Sincronia("busca.documentos", ["tipo", "chave"]),
    Sincronia("gold.dim_campus", ["campus"]),
    Sincronia("gold.dim_curso", ["nome_curso"]),
    Sincronia("gold.dim_tempo", ["sk_tempo"]),
    Sincronia("gold.dim_perfil_social", ["perfil_macro", "categoria_cota", "faixa_renda", "is_cotista"],
              conflito="ON CONSTRAINT uk_dim_perfil_social"),
    Sincronia(
        "gold.fato_retencao_curso", ["sk_curso", "sk_campus"],
        exportar=f"""
            SELECT c.nome_curso, camp.campus, {', '.join('f.' + m for m in MEDIDAS_RETENCAO)}
            FROM gold.fato_retencao_curso f
            JOIN gold.dim_curso c USING (sk_curso)
            JOIN gold.dim_campus camp USING (sk_campus)""",
        inserir=f"""
            SELECT c.sk_curso, camp.sk_campus, {', '.join('tmp.' + m for m in MEDIDAS_RETENCAO)}
            FROM tmp
            JOIN gold.dim_curso c ON c.nome_curso = tmp.nome_curso
            JOIN gold.dim_campus camp ON camp.campus = tmp.campus""",
        colunas=["sk_curso", "sk_campus", *MEDIDAS_RETENCAO],
    ),
    Sincronia(
        "gold.fato_alunos_ativos", ["sk_curso"],
        exportar=f"""
            SELECT c.nome_curso, {', '.join('f.' + m for m in MEDIDAS_ATIVOS)}
            FROM gold.fato_alunos_ativos f
            JOIN gold.dim_curso c USING (sk_curso)""",
        inserir=f"""
            SELECT c.sk_curso, {', '.join('tmp.' + m for m in MEDIDAS_ATIVOS)}
            FROM tmp
            JOIN gold.dim_curso c ON c.nome_curso = tmp.nome_curso""",
        colunas=["sk_curso", *MEDIDAS_ATIVOS],
    ),
]


def colunas_copiaveis(conn: psycopg.Connection, tabela: str) -> List[str]:
    esquema, nome = tabela.split(".")
    linhas = conn.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s AND is_identity = 'NO' AND is_generated = 'NEVER'
        ORDER BY ordinal_position
        """,
        (esquema, nome),
    ).fetchall()
    return [c for (c,) in linhas if c not in CARIMBOS]


def tem_coluna(conn: psycopg.Connection, tabela: str, coluna: str) -> bool:
    esquema, nome = tabela.split(".")
    return conn.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s)",
        (esquema, nome, coluna),
    ).fetchone()[0]


def sincronizar_tabela(origem: psycopg.Connection, destino: psycopg.Connection, s: Sincronia,
                       somente_inserir: bool) -> Tuple[int, int]:
    """Copia a tabela para `tmp` no destino e mescla pela chave. Devolve (inseridas, atualizadas)."""
    colunas = s.colunas or colunas_copiaveis(origem, s.tabela)
    exportar = s.exportar or f"SELECT {', '.join(colunas)} FROM {s.tabela}"
    inserir = s.inserir or f"SELECT {', '.join(colunas)} FROM tmp"

    destino.execute("DROP TABLE IF EXISTS tmp")
    destino.execute(f"CREATE TEMP TABLE tmp ON COMMIT DROP AS {exportar} WITH NO DATA")
    with origem.cursor().copy(f"COPY ({exportar}) TO STDOUT") as saida, \
            destino.cursor().copy("COPY tmp FROM STDIN") as entrada:
        for bloco in saida:
            entrada.write(bloco)

    alvo = s.conflito or f"({', '.join(s.chave)})"
    valores = [c for c in colunas if c not in s.chave]
    if somente_inserir or not valores:
        acao = "DO NOTHING"
    else:
        sets = [f"{c} = EXCLUDED.{c}" for c in valores]
        sets += [f"{c} = now()" for c in CARIMBOS if tem_coluna(destino, s.tabela, c)]
        mudou = (f"({', '.join('t.' + c for c in valores)}) IS DISTINCT FROM "
                 f"({', '.join('EXCLUDED.' + c for c in valores)})")
        acao = f"DO UPDATE SET {', '.join(sets)} WHERE {mudou}"

    # xmax = 0 só na linha recém-inserida; a atualizada carrega o xmax da versão anterior.
    resultado = destino.execute(
        f"""
        INSERT INTO {s.tabela} AS t ({', '.join(colunas)})
        {inserir}
        ON CONFLICT {alvo} {acao}
        RETURNING (xmax = 0)
        """
    ).fetchall()
    inseridas = sum(1 for (novo,) in resultado if novo)
    return inseridas, len(resultado) - inseridas


def sincronizar(url_destino: str, somente_inserir: bool = False) -> Dict[str, Tuple[int, int]]:
    aplicar_migracoes(url_destino)
    resumo = {}
    with conectar() as origem, conectar(url_destino, autocommit=True) as destino:
        with destino.transaction():
            for s in SINCRONIAS:
                resumo[s.tabela] = sincronizar_tabela(origem, destino, s, somente_inserir)
        destino.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY gold.mv_dashboard_executivo")
    for tabela, (inseridas, atualizadas) in resumo.items():
        logger.info(f"{tabela}: {inseridas:,} inseridas, {atualizadas:,} atualizadas.")
    return resumo


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--somente-inserir", action="store_true",
                        help="Não atualiza linhas que já existem no Supabase, mesmo que tenham mudado.")
    args = parser.parse_args(argv)

    url_destino = ler_variavel("SUPABASE_DATABASE_URL")
    if not url_destino:
        logger.warning("SUPABASE_DATABASE_URL não definida: sincronização com o Supabase pulada.")
        return
    if url_destino == database_url():
        # Origem e destino iguais: o .env antigo punha a URL do Supabase em DATABASE_URL.
        raise SystemExit("DATABASE_URL e SUPABASE_DATABASE_URL apontam para o mesmo banco. "
                         "DATABASE_URL deve ser o banco local do pipeline.")
    sincronizar(url_destino, args.somente_inserir)


if __name__ == "__main__":
    main()

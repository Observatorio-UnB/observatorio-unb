"""
Demonstra o tratamento de dado atrasado, da carga ao lago: a chegada é classificada pela marca
d'água, a gold é recalculada e só a janela do lago que recebeu o dado é regravada.

Simula duas publicações do SIGAA sobre silver.discentes_graduacao, a tabela que alimenta a
Silver 3NF. Em cada uma, N vínculos ativos de uma coorte viram formados, com diploma registrado:
  1. no prazo: coorte 2019, diploma de agosto de 2024 (2024/1, período ainda aberto);
  2. atrasada: coorte 2012, diploma de março de 2023 (2022/2, período já fechado), que entrou
     no sistema depois da publicação anterior.
Depois de cada uma: recarga da Silver 3NF e do Star Schema (src/db/povoar_dimensional.py), o
que chegou na carga (silver.chegadas_por_carga) e o export do lago só das janelas alteradas.

No fim, mesmo se a demonstração falhar no meio, a silver volta ao estado de antes, a Silver 3NF
e o lago são refeitos, e as cargas simuladas saem de silver.cargas_vinculos.

Requer o pipeline rodado (scripts/rodar_pipeline.sh).

Uso:
    python3 src/db/demonstrar_dado_atrasado.py
"""

import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Set

from deltalake import DeltaTable

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import exportar_lago as lago  # noqa: E402
from src.db.conexao import conectar  # noqa: E402
from src.db.dado_atrasado import marca_dagua, resumo, rotulo  # noqa: E402
from src.db.povoar_dimensional import executar_elt_dimensional  # noqa: E402

VINCULOS_POR_PUBLICACAO = 20

PUBLICACOES = (
    ("no prazo", 2019, date(2024, 8, 20)),
    ("atrasada", 2012, date(2023, 3, 10)),
)

COLUNAS = (
    "status_aluno", "tipo_saida_grupo", "data_registro_diploma", "ano_saida", "semestre_saida",
    "periodo_saida_estimado", "semestres_permanencia", "semestres_permanencia_valida",
)

# Mesmas regras de transform_silver.py: semestre_pela_data_do_diploma (jan-abr -> 2º semestre do
# ano anterior, mai-out -> 1º, nov-dez -> 2º) e _permanencia.
SQL_FORMAR = """
WITH saida AS (
    SELECT CASE WHEN extract(month FROM %(diploma)s::date) <= 4 THEN extract(year FROM %(diploma)s::date) - 1
                ELSE extract(year FROM %(diploma)s::date) END::smallint AS ano,
           CASE WHEN extract(month FROM %(diploma)s::date) BETWEEN 5 AND 10 THEN 1 ELSE 2 END::smallint AS semestre
)
UPDATE silver.discentes_graduacao dg
SET status_aluno = 'CONCLUÍDO', tipo_saida_grupo = 'FORMATURA', data_registro_diploma = %(diploma)s,
    ano_saida = s.ano, semestre_saida = s.semestre, periodo_saida_estimado = true,
    semestres_permanencia = 2 * (s.ano - dg.ano_ingresso) + s.semestre,
    semestres_permanencia_valida = CASE WHEN 2 * (s.ano - dg.ano_ingresso) + s.semestre BETWEEN 1 AND 30
                                        THEN 2 * (s.ano - dg.ano_ingresso) + s.semestre END
FROM saida s
WHERE dg.id = ANY(%(ids)s)
"""

SQL_GOLD = """
SELECT sk_curso, total_formados, total_ainda_ativos FROM gold.fato_retencao_curso
"""


def escolher_vinculos(coorte: int) -> List[int]:
    """Vínculos ativos do SIGAA na coorte, os prestes a se formar primeiro."""
    with conectar() as conn:
        ids = [i for (i,) in conn.execute(
            """
            SELECT id FROM silver.discentes_graduacao
            WHERE fonte = 'SIGAA' AND tipo_saida_grupo = 'ATIVO' AND ano_ingresso = %s
            ORDER BY status_aluno = 'ATIVO - FORMANDO' DESC, id
            LIMIT %s
            """,
            (coorte, VINCULOS_POR_PUBLICACAO),
        ).fetchall()]
    if len(ids) < VINCULOS_POR_PUBLICACAO:
        raise RuntimeError(f"A coorte {coorte} tem só {len(ids)} vínculos ativos no SIGAA. Rode o pipeline antes.")
    return ids


def arquivos_por_janela() -> Dict[int, Set[str]]:
    caminho = lago.LAGO_DIR / "silver" / "movimentacoes_vinculos"
    arquivos = defaultdict(set)
    for uri in DeltaTable(str(caminho)).file_uris():
        particao = Path(uri).parent.name
        arquivos[int(particao.split("=")[1])].add(uri)
    return arquivos


def recarregar() -> int:
    """Recarga da Silver 3NF e do Star Schema e export do que mudou; devolve o id da carga."""
    executar_elt_dimensional()
    lago.exportar(so_alteradas=True)
    with conectar() as conn:
        return conn.execute("SELECT max(id_carga) FROM silver.cargas_vinculos").fetchone()[0]


def publicar(nome: str, coorte: int, diploma: date, ids: List[int]) -> None:
    with conectar() as conn:
        gold_antes = set(conn.execute(SQL_GOLD).fetchall())
        conn.execute(SQL_FORMAR, {"diploma": diploma, "ids": ids})
    arquivos_antes = arquivos_por_janela()

    id_carga = recarregar()

    with conectar() as conn:
        marca = conn.execute(
            "SELECT marca_dagua FROM silver.cargas_vinculos WHERE id_carga < %s ORDER BY id_carga DESC LIMIT 1",
            (id_carga,),
        ).fetchone()[0]
        chegadas = resumo(conn, id_carga)
        cursos_revisados = len({sk for sk, *_ in set(conn.execute(SQL_GOLD).fetchall()) - gold_antes})
    arquivos_depois = arquivos_por_janela()
    regravadas = sorted(q for q in arquivos_antes.keys() | arquivos_depois.keys()
                        if arquivos_antes.get(q) != arquivos_depois.get(q))
    intactas = sorted(arquivos_antes.keys() - set(regravadas))

    print(f"\nPublicação {nome}: {len(ids)} formaturas da coorte {coorte}, diploma de {diploma:%d/%m/%Y}")
    print(f"  carga {id_carga}; marca d'água da carga anterior: {rotulo(marca)}")
    for quinquenio, chegada, a_mais, a_menos, coortes in chegadas:
        publicada = f"   revisa {coortes} coorte já publicada" if coortes else ""
        print(f"  quinquênio {quinquenio}  {chegada:<12}{a_mais - a_menos:>+5}{publicada}")
    print(f"  gold: {cursos_revisados} curso(s) com contagem revisada em gold.fato_retencao_curso")
    print(f"  lago: janela(s) regravada(s) {regravadas}; sem arquivo novo {intactas}")


def demonstrar() -> None:
    escolhidos = {coorte: escolher_vinculos(coorte) for _, coorte, _ in PUBLICACOES}
    todos = [i for ids in escolhidos.values() for i in ids]
    with conectar() as conn:
        originais = conn.execute(
            f"SELECT id, {', '.join(COLUNAS)} FROM silver.discentes_graduacao WHERE id = ANY(%s)", (todos,)
        ).fetchall()

    id_base = recarregar()
    with conectar() as conn:
        publicada_em = conn.execute(
            "SELECT publicada_em FROM silver.cargas_vinculos WHERE id_carga = %s", (id_base,)).fetchone()[0]
    print(f"Carga de referência {id_base}: publicação de {publicada_em:%d/%m/%Y}, "
          f"marca d'água {rotulo(marca_dagua(publicada_em))}")
    try:
        for nome, coorte, diploma in PUBLICACOES:
            publicar(nome, coorte, diploma, escolhidos[coorte])
    finally:
        with conectar() as conn:
            conn.cursor().executemany(
                f"UPDATE silver.discentes_graduacao SET {', '.join(f'{c} = %s' for c in COLUNAS)} WHERE id = %s",
                [(*linha[1:], linha[0]) for linha in originais],
            )
        recarregar()
        with conectar() as conn:
            conn.execute("DELETE FROM silver.cargas_vinculos WHERE id_carga > %s", (id_base,))
        print(f"\nSilver, Silver 3NF e lago de volta ao estado da carga {id_base}; cargas simuladas removidas.")


if __name__ == "__main__":
    # As etapas chamadas logam cada tabela gravada, e a carga avisa da chegada atrasada (também a
    # da restauração). O resumo impresso aqui já traz o que importa.
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("dado_atrasado").setLevel(logging.ERROR)
    demonstrar()

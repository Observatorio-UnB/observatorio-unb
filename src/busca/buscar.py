"""
Busca semântica em busca.documentos.

A consulta é vetorizada com o mesmo modelo dos documentos e comparada por
distância de cosseno (operador <=> do pgvector).

Uso:
    python3 src/busca/buscar.py "cursos noturnos com muita evasão"
    python3 src/busca/buscar.py "inteligência artificial na saúde" --tipo projeto_pibic -k 10
"""

import argparse
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.busca.vetorizar import TIPOS, carregar_modelo, gerar_embeddings, nome_do_modelo, vetor_literal  # noqa: E402
from src.db.conexao import conectar  # noqa: E402


@lru_cache(maxsize=1)
def _modelo():
    return carregar_modelo(nome_do_modelo())


def buscar(consulta: str, k: int = 5, tipo: Optional[str] = None) -> List[Dict]:
    """Os k documentos mais próximos da consulta, do mais para o menos similar."""
    if tipo is not None and tipo not in TIPOS:
        raise ValueError(f"tipo deve ser um de {TIPOS}")
    vetor = vetor_literal(gerar_embeddings(_modelo(), [consulta])[0])
    with conectar() as conn:
        with conn.transaction():
            # Com filtro por tipo, o índice HNSW sozinho devolveria os vizinhos de todos
            # os tipos e o WHERE descartaria a maioria (ex.: 88 cursos entre 13 mil
            # documentos). A varredura iterativa (pgvector >= 0.8) continua buscando até
            # completar os k resultados.
            conn.execute("SET LOCAL hnsw.iterative_scan = strict_order")
            linhas = conn.execute(
                """
                SELECT tipo, titulo, conteudo, metadados, 1 - (embedding <=> %(v)s::vector) AS similaridade
                FROM busca.documentos
                WHERE %(tipo)s::text IS NULL OR tipo = %(tipo)s::text
                ORDER BY embedding <=> %(v)s::vector
                LIMIT %(k)s
                """,
                {"v": vetor, "tipo": tipo, "k": k},
            ).fetchall()
    return [
        {"tipo": t, "titulo": ti, "conteudo": c, "metadados": m, "similaridade": round(float(s), 4)}
        for t, ti, c, m, s in linhas
    ]


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("consulta", help="Pergunta ou tema, em linguagem natural.")
    parser.add_argument("-k", type=int, default=5, help="Número de resultados (padrão: 5).")
    parser.add_argument("--tipo", choices=TIPOS, help="Restringe a um tipo de documento.")
    args = parser.parse_args(argv)

    for i, r in enumerate(buscar(args.consulta, args.k, args.tipo), start=1):
        print(f"{i}. [{r['tipo']}] {r['titulo']}  (similaridade {r['similaridade']:.3f})")
        print(f"   {r['conteudo'][:220].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()

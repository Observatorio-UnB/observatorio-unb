"""
Busca semântica em busca.documentos.

A busca é híbrida, com três listas de candidatos (migração 0026):
  - vetorial: a consulta é vetorizada com o mesmo modelo dos documentos e comparada por distância
    de cosseno (operador <=> do pgvector);
  - texto completo: trechos com ao menos metade dos termos da consulta, em português, no título e no
    conteúdo, ordenados por ts_rank_cd; acha o termo técnico que o embedding dilui ("SLA de frescor");
  - título: trigramas da consulta no título (pg_trgm), com o título que contém a consulta inteira
    primeiro; acha sigla, número e nome exato ("ADR 0028", o título de um plano de IC).
As listas são combinadas por Reciprocal Rank Fusion (RRF): cada documento soma
peso / (RRF_K + posição) em cada lista em que aparece.

Só entra documento com evidência: similaridade de cosseno de ao menos SIMILARIDADE_MINIMA, título
que casa (similaridade de palavra de ao menos SIMILARIDADE_TEXTO_MINIMA) ou texto com os termos. Se
a consulta tem evidência em algum documento, os vizinhos vetoriais a partir de
SIMILARIDADE_COM_EVIDENCIA também entram. Uma consulta sem relação com nada ("lorem ipsum dolor")
devolve lista vazia, e não os k menos distantes.

Uso:
    python3 src/busca/buscar.py "cursos noturnos com muita evasão"
    python3 src/busca/buscar.py "inteligência artificial na saúde" --tipo projeto_pibic -k 10
"""

import argparse
import math
import sys
import unicodedata
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional

from pgvector.psycopg import register_vector
from psycopg import sql

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.busca.vetorizar import TIPOS, carregar_modelo, gerar_embeddings, nome_do_modelo  # noqa: E402
from src.db.conexao import conectar  # noqa: E402

# Calibrados com tests/test_banco_busca.py. A similaridade de cosseno sozinha não separa acerto de
# ruído: os documentos esperados ficaram entre 0,29 e 0,81, e consultas sem sentido ("lorem ipsum",
# "o rato roeu a roupa") chegaram a 0,53. Por isso o vetor só basta acima de 0,55; abaixo disso, o
# documento precisa que a consulta tenha evidência de texto em algum lugar.
SIMILARIDADE_MINIMA = 0.55
SIMILARIDADE_COM_EVIDENCIA = 0.45
SIMILARIDADE_TEXTO_MINIMA = 0.8
# Candidatos de cada lista antes da fusão, e a constante do RRF (60, a do artigo original).
CANDIDATOS = 30
RRF_K = 60
PESO_TEXTO_COMPLETO = 1.0
PESO_TITULO = 1.0
# Fração dos termos da consulta que um trecho precisa ter para entrar pela busca em texto completo.
# Acima de MAXIMO_TERMOS termos, só os primeiros contam (as combinações crescem rápido).
COBERTURA_MINIMA = 0.5
MAXIMO_TERMOS = 8


@lru_cache(maxsize=1)
def modelo():
    """Modelo de embedding, carregado (e baixado, na primeira vez) uma vez por processo."""
    return carregar_modelo(nome_do_modelo())


def sem_acento(texto: str) -> str:
    # Os títulos de curso e de plano de IC vêm sem acento da silver; a documentação, com acento.
    # A busca por texto tenta a consulta das duas formas.
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def consulta_de_cobertura(termos: List[str], cobertura: Optional[float] = None) -> Optional[str]:
    """tsquery que casa com o texto que tem ao menos `cobertura` dos termos (padrão:
    COBERTURA_MINIMA, arredondada para cima; 0 é qualquer termo). É um OU das combinações de termos
    desse tamanho: com 4 termos e metade, (a & b) | (a & c) | ... O índice GIN resolve direto, e um
    termo solto ("dolor" de "lorem ipsum dolor") não basta.

    Sem termos (só palavras vazias), devolve None: `texto_busca @@ NULL` não casa com nada."""
    cobertura = COBERTURA_MINIMA if cobertura is None else cobertura
    termos = sorted(set(termos))[:MAXIMO_TERMOS]
    if not termos:
        return None
    citados = ["'" + t.replace("'", "''") + "'" for t in termos]
    tamanho = max(1, math.ceil(len(citados) * cobertura))
    return " | ".join("(" + " & ".join(c) + ")" for c in combinations(citados, tamanho))


def buscar(consulta: str, k: int = 5, tipo: Optional[str] = None) -> List[Dict]:
    """Os k documentos mais relevantes para a consulta, do mais para o menos relevante."""
    if tipo is not None and tipo not in TIPOS:
        raise ValueError(f"tipo deve ser um de {TIPOS}")
    vetor = gerar_embeddings(modelo(), [consulta])[0]
    # O filtro só entra quando há tipo: com ele, o planejador sabe o tipo e usa documentos_tipo_idx.
    filtro = sql.SQL("AND tipo = %(tipo)s") if tipo else sql.SQL("")
    consulta_sql = sql.SQL(
        """
        WITH vetorial AS (
            SELECT id, row_number() OVER (ORDER BY distancia) AS posicao,
                   1 - distancia >= %(min_vetor)s AS forte,
                   1 - distancia >= %(min_vetor_com_evidencia)s AS proximo
            FROM (
                SELECT id, embedding <=> %(v)s AS distancia
                FROM busca.documentos
                WHERE true {filtro}
                ORDER BY embedding <=> %(v)s
                LIMIT %(n)s
            ) candidatos
        ),
        texto_completo AS (
            -- Achados pela consulta de cobertura (metade dos termos, montada em consulta_de_cobertura)
            -- e ordenados pelo ts_rank_cd de qualquer termo.
            SELECT id, row_number() OVER (ORDER BY nota DESC) AS posicao
            FROM (
                SELECT id, ts_rank_cd(texto_busca, %(qualquer_termo)s::tsquery) AS nota
                FROM busca.documentos
                WHERE texto_busca @@ %(cobertura)s::tsquery {filtro}
                ORDER BY nota DESC
                LIMIT %(n)s
            ) candidatos
        ),
        titulo AS (
            SELECT id, row_number() OVER (ORDER BY contem DESC, nota DESC) AS posicao,
                   contem OR nota >= 0.99 AS exato
            FROM (
                SELECT id,
                       greatest(word_similarity(%(q)s, titulo), word_similarity(%(q_sem_acento)s, titulo)) AS nota,
                       strpos(lower(titulo), lower(%(q)s)) > 0
                         OR strpos(lower(titulo), lower(%(q_sem_acento)s)) > 0 AS contem
                FROM busca.documentos
                WHERE (%(q)s <%% titulo OR %(q_sem_acento)s <%% titulo) {filtro}
                ORDER BY contem DESC, nota DESC
                LIMIT %(n)s
            ) candidatos
            WHERE nota >= %(min_texto)s
        )
        SELECT tipo, titulo, conteudo, metadados, similaridade, relevancia
        FROM (
        -- Um trecho por arquivo da documentação, o mais relevante: sem isso, as seções de um mesmo
        -- arquivo ocupam o top k e empurram os outros arquivos para fora.
        SELECT DISTINCT ON (coalesce(d.metadados->>'arquivo', d.id::text))
               d.tipo, d.titulo, d.conteudo, d.metadados,
               1 - (d.embedding <=> %(v)s) AS similaridade,
               coalesce(1.0 / (%(rrf_k)s + v.posicao), 0)
                 + coalesce(%(peso_completo)s / (%(rrf_k)s + c.posicao), 0)
                 + coalesce(%(peso_titulo)s / (%(rrf_k)s + t.posicao), 0)
                 -- Título que contém a consulta inteira ("ADR 0028", o nome do curso) vale como mais
                 -- uma lista em que ele é o primeiro: o conteúdo raramente repete o próprio título.
                 + CASE WHEN t.exato THEN 1.0 / (%(rrf_k)s + 1) ELSE 0 END AS relevancia
        FROM vetorial v
        FULL JOIN titulo t USING (id)
        FULL JOIN texto_completo c USING (id)
        JOIN busca.documentos d USING (id)
        -- Só entra quem tem evidência: vetor forte, título que casa ou texto com os termos. Se a
        -- consulta tem evidência em algum documento, é uma pergunta de verdade, e o vizinho vetorial
        -- próximo também entra. A posição vetorial de quem entrou pelo texto ainda conta na ordem.
        WHERE v.forte OR t.id IS NOT NULL OR c.id IS NOT NULL
           OR (v.proximo AND (EXISTS (SELECT 1 FROM vetorial WHERE forte)
                              OR EXISTS (SELECT 1 FROM titulo) OR EXISTS (SELECT 1 FROM texto_completo)))
        ORDER BY coalesce(d.metadados->>'arquivo', d.id::text), relevancia DESC, similaridade DESC
        ) por_arquivo
        ORDER BY relevancia DESC, similaridade DESC
        LIMIT %(k)s
        """
    ).format(filtro=filtro)
    parametros = {
        "v": vetor, "q": consulta, "q_sem_acento": sem_acento(consulta), "tipo": tipo, "k": k,
        "n": max(CANDIDATOS, k), "min_vetor": SIMILARIDADE_MINIMA,
        "min_vetor_com_evidencia": SIMILARIDADE_COM_EVIDENCIA, "min_texto": SIMILARIDADE_TEXTO_MINIMA,
        "rrf_k": RRF_K, "peso_completo": PESO_TEXTO_COMPLETO, "peso_titulo": PESO_TITULO,
    }
    with conectar() as conn:
        register_vector(conn)  # o vetor vai em binário, sem passar por texto
        with conn.cursor() as cur:
            with conn.transaction():
                # Com filtro por tipo, o índice HNSW sozinho devolveria os vizinhos de todos
                # os tipos e o WHERE descartaria a maioria (ex.: 88 cursos entre 13 mil
                # documentos). A varredura iterativa (pgvector >= 0.8) continua buscando até
                # completar os candidatos.
                cur.execute("SET LOCAL hnsw.iterative_scan = strict_order")
                # O padrão (40) deixava o HNSW longe da busca exata: numa consulta, o melhor vizinho
                # achado tinha 0,37 de similaridade, e o exato, 0,42. Com 13 mil documentos, 200 custa
                # poucos milissegundos e devolve os mesmos vizinhos da busca exata.
                cur.execute("SET LOCAL hnsw.ef_search = 200")
                # Os termos da consulta já reduzidos ao radical, sem palavras vazias ("de", "nos").
                termos = cur.execute(
                    "SELECT tsvector_to_array(to_tsvector('portuguese', %s))", (consulta,)
                ).fetchone()[0]
                parametros["cobertura"] = consulta_de_cobertura(termos)
                parametros["qualquer_termo"] = consulta_de_cobertura(termos, 0)
                linhas = cur.execute(consulta_sql, parametros).fetchall()
    return [
        {"tipo": t, "titulo": ti, "conteudo": c, "metadados": m,
         "similaridade": round(float(s), 4), "relevancia": round(float(r), 5)}
        for t, ti, c, m, s, r in linhas
    ]


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("consulta", help="Pergunta ou tema, em linguagem natural.")
    parser.add_argument("-k", type=int, default=5, help="Número de resultados (padrão: 5).")
    parser.add_argument("--tipo", choices=TIPOS, help="Restringe a um tipo de documento.")
    args = parser.parse_args(argv)

    resultados = buscar(args.consulta, args.k, args.tipo)
    if not resultados:
        print("Nenhum documento relevante para a consulta.")
    for i, r in enumerate(resultados, start=1):
        print(f"{i}. [{r['tipo']}] {r['titulo']}  (similaridade {r['similaridade']:.3f})")
        print(f"   {r['conteudo'][:220].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()

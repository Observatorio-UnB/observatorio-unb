"""
Busca semântica em busca.documentos.

A busca é híbrida, com três listas de candidatos (migrações 0026 e 0032):
  - vetorial: a consulta (expandida com siglas/sinônimos da UnB) é vetorizada com o mesmo modelo
    dos documentos e comparada por distância de cosseno (operador <=> do pgvector);
  - texto completo: trechos com ao menos metade dos termos da consulta (sem acento, em português,
    com peso A no título e peso B no conteúdo), ordenados por ts_rank_cd;
  - título: trigramas da consulta no título (pg_trgm), com o título que contém a consulta inteira
    primeiro; acha sigla, número e nome exato ("ADR 0028", o título de um plano de IC).
As listas são combinadas por Reciprocal Rank Fusion (RRF): cada documento soma
peso / (RRF_K + posição) em cada lista em que aparece.

Suporta filtros facetados (campus, turno, área, classificação de retenção, faixa de evasão,
intervalo de anos de PIBIC), retorna explicabilidade (quais sinais casaram) e trechos destacados
com `ts_headline`.

Uso:
    python3 src/busca/buscar.py "cursos noturnos com muita evasão"
    python3 src/busca/buscar.py "inteligência artificial na saúde" --tipo projeto_pibic -k 10
"""

import argparse
import math
import re
import sys
import unicodedata
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pgvector.psycopg.vector import register_vector_info
from psycopg import sql
from psycopg.types import TypeInfo

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.busca.vetorizar import (  # noqa: E402
    TIPOS,
    carregar_modelo,
    gerar_embeddings,
    nome_do_modelo,
    normalizar_campus,
)
from src.db.conexao import conexao_do_pool  # noqa: E402

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

# Dicionário determinístico de siglas e sinônimos do domínio UnB / Observatório.
# Cada chave (minúscula, sem acento) adiciona termos equivalentes para enriquecer o embedding e o FTS.
SINONIMOS_UNB: Dict[str, str] = {
    "deg": "decanato ensino graduacao",
    "nde": "nucleo docente estruturante matriz curricular",
    "abi": "area basica ingresso curso tronco",
    "irc": "indice retencao critica",
    "pibic": "iniciacao cientifica bolsa",
    "pivic": "iniciacao cientifica voluntaria",
    "fga": "gama fcte engenharia",
    "fcte": "gama fga engenharia",
    "gama": "fga fcte",
    "fce": "ceilandia fcts saude",
    "fcts": "ceilandia fce saude",
    "ceilandia": "fce fcts",
    "fup": "planaltina",
    "planaltina": "fup",
    "darcy": "darcy ribeiro plano piloto",
    "sigra": "sistema academico historico",
    "sigaa": "sistema academico atual",
    "ppi": "pretos pardos indigenas cotas",
    "scd": "dimensao variacao lenta vigencia",
    "lgpd": "privacidade anonimato dados pessoais",
    "desligamento": "evasao",
    "abandono": "evasao",
    "trancamento": "evasao retencao",
    "jubilamento": "retencao atraso prazo maximo",
    "jubila": "retencao atraso prazo maximo",
}


@lru_cache(maxsize=1)
def modelo():
    """Modelo de embedding, carregado (e baixado, na primeira vez) uma vez por processo."""
    return carregar_modelo(nome_do_modelo())


def sem_acento(texto: str) -> str:
    # Os títulos de curso e de plano de IC vêm sem acento da silver; a documentação, com acento.
    # A busca por texto tenta a consulta das duas formas.
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def expandir_consulta(consulta: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Expande siglas e termos de domínio da UnB de forma determinística.

    Devolve `(consulta_expandida, [(sigla_encontrada, expansao), ...])`.
    """
    tokens = re.findall(r"[a-zA-Z0-9À-ÿ]+", consulta)
    vistos = set()
    expansoes: List[Tuple[str, str]] = []
    extra: List[str] = []
    base_norm = sem_acento(consulta).lower()

    for tok in tokens:
        chave = sem_acento(tok).lower()
        if chave in SINONIMOS_UNB and chave not in vistos:
            vistos.add(chave)
            exp = SINONIMOS_UNB[chave]
            # Só adiciona palavras que ainda não aparecem na consulta original
            novas = [p for p in exp.split() if p not in base_norm.split()]
            if novas:
                expansoes.append((tok, " ".join(novas)))
                extra.extend(novas)

    if not extra:
        return consulta, []
    return f"{consulta} {' '.join(dict.fromkeys(extra))}", expansoes


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


def _montar_filtros_sql(
    tipo: Optional[str],
    tipos: Optional[Iterable[str]],
    filtros: Optional[Dict[str, Any]],
) -> Tuple[sql.Composed, Dict[str, Any]]:
    """Monta cláusulas WHERE reutilizáveis nas 3 CTEs (vetorial, texto_completo, titulo)."""
    clausulas: List[sql.Composable] = []
    params: Dict[str, Any] = {}

    if tipo is not None:
        if tipo not in TIPOS:
            raise ValueError(f"tipo deve ser um de {TIPOS}")
        clausulas.append(sql.SQL("AND tipo = %(tipo)s"))
        params["tipo"] = tipo
    elif tipos is not None:
        lista_tipos = list(tipos)
        desconhecidos = set(lista_tipos) - set(TIPOS)
        if desconhecidos:
            raise ValueError(f"tipos desconhecidos: {sorted(desconhecidos)}. Use {TIPOS}.")
        if lista_tipos:
            clausulas.append(sql.SQL("AND tipo = ANY(%(tipos)s)"))
            params["tipos"] = lista_tipos

    f = filtros or {}
    if f.get("campus"):
        campus_norm = normalizar_campus(str(f["campus"]))
        # Compatível tanto com documentos já revetorizados (metadados->>'campus_norm')
        # quanto com documentos antigos (match por padrão no metadados->>'campus').
        clausulas.append(
            sql.SQL(
                "AND (metadados->>'campus_norm' = %(campus_norm)s "
                "OR upper(coalesce(metadados->>'campus', '')) LIKE %(campus_like)s)"
            )
        )
        params["campus_norm"] = campus_norm
        if "GAMA" in campus_norm:
            params["campus_like"] = "%FCTE%"
        elif "CEIL" in campus_norm:
            params["campus_like"] = "%FCTS%"
        elif "PLANALTINA" in campus_norm:
            params["campus_like"] = "%FUP%"
        elif "DARCY" in campus_norm:
            params["campus_like"] = "%DARCY%"
        else:
            params["campus_like"] = f"%{campus_norm}%"

    if f.get("turno"):
        clausulas.append(sql.SQL("AND metadados->>'turno' = %(turno)s"))
        params["turno"] = str(f["turno"])

    if f.get("area_conhecimento"):
        clausulas.append(sql.SQL("AND metadados->>'area_conhecimento' = %(area_conhecimento)s"))
        params["area_conhecimento"] = str(f["area_conhecimento"])

    if f.get("classificacao_retencao"):
        clausulas.append(sql.SQL("AND metadados->>'classificacao_retencao' = %(classificacao_retencao)s"))
        params["classificacao_retencao"] = str(f["classificacao_retencao"])

    if f.get("evasao_min") is not None:
        clausulas.append(
            sql.SQL("AND (metadados->>'taxa_evasao_pct')::numeric >= %(evasao_min)s")
        )
        params["evasao_min"] = float(f["evasao_min"])

    if f.get("evasao_max") is not None:
        clausulas.append(
            sql.SQL("AND (metadados->>'taxa_evasao_pct')::numeric <= %(evasao_max)s")
        )
        params["evasao_max"] = float(f["evasao_max"])

    if f.get("ano_min") is not None:
        clausulas.append(sql.SQL("AND (metadados->>'ano')::int >= %(ano_min)s"))
        params["ano_min"] = int(f["ano_min"])

    if f.get("ano_max") is not None:
        clausulas.append(sql.SQL("AND (metadados->>'ano')::int <= %(ano_max)s"))
        params["ano_max"] = int(f["ano_max"])

    return sql.SQL(" ").join(clausulas), params


def _resumir_fontes(pos_v, pos_c, pos_t, exato: bool) -> List[str]:
    fontes = []
    if exato:
        fontes.append("titulo_exato")
    elif pos_t is not None:
        fontes.append("titulo")
    if pos_c is not None:
        fontes.append("texto")
    if pos_v is not None:
        fontes.append("vetorial")
    return fontes


def buscar(
    consulta: str,
    k: int = 5,
    tipo: Optional[str] = None,
    tipos: Optional[Iterable[str]] = None,
    filtros: Optional[Dict[str, Any]] = None,
    url: Optional[str] = None,
) -> List[Dict]:
    """Os k documentos mais relevantes para a consulta, do mais para o menos relevante.
    `url`: banco a consultar (padrão: DATABASE_URL); o chat passa a do usuário somente leitura."""
    consulta_expandida, expansoes = expandir_consulta(consulta)
    vetor = gerar_embeddings(modelo(), [consulta_expandida])[0]

    filtro_sql, params_filtro = _montar_filtros_sql(tipo, tipos, filtros)
    tem_filtro_facetado = bool(filtros and any(v is not None and v != "" for v in filtros.values()))

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
            -- Achados pela consulta de cobertura (metade dos termos, sem acento)
            -- e ordenados pelo ts_rank_cd de qualquer termo (título peso A, conteúdo peso B).
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
        ),
        ranqueados AS (
            SELECT tipo, chave, titulo, conteudo, metadados, similaridade, relevancia,
                   pos_v, pos_c, pos_t, exato
            FROM (
            -- Um trecho por arquivo da documentação, o mais relevante: sem isso, as seções de um mesmo
            -- arquivo ocupam o top k e empurram os outros arquivos para fora.
            SELECT DISTINCT ON (coalesce(d.metadados->>'arquivo', d.id::text))
                   d.tipo, d.chave, d.titulo, d.conteudo, d.metadados,
                   1 - (d.embedding <=> %(v)s) AS similaridade,
                   coalesce(1.0 / (%(rrf_k)s + v.posicao), 0)
                     + coalesce(%(peso_completo)s / (%(rrf_k)s + c.posicao), 0)
                     + coalesce(%(peso_titulo)s / (%(rrf_k)s + t.posicao), 0)
                     -- Título que contém a consulta inteira ("ADR 0028", o nome do curso) vale como mais
                     -- uma lista em que ele é o primeiro: o conteúdo raramente repete o próprio título.
                     + CASE WHEN t.exato THEN 1.0 / (%(rrf_k)s + 1) ELSE 0 END AS relevancia,
                   v.posicao AS pos_v,
                   c.posicao AS pos_c,
                   t.posicao AS pos_t,
                   coalesce(t.exato, false) AS exato
            FROM vetorial v
            FULL JOIN titulo t USING (id)
            FULL JOIN texto_completo c USING (id)
            JOIN busca.documentos d USING (id)
            WHERE v.forte OR t.id IS NOT NULL OR c.id IS NOT NULL
               OR (v.proximo AND (EXISTS (SELECT 1 FROM vetorial WHERE forte)
                                  OR EXISTS (SELECT 1 FROM titulo)
                                  OR EXISTS (SELECT 1 FROM texto_completo)
                                  OR %(relaxar_com_filtro)s))
            ORDER BY coalesce(d.metadados->>'arquivo', d.id::text), relevancia DESC, similaridade DESC
            ) por_arquivo
            ORDER BY relevancia DESC, similaridade DESC
            LIMIT %(k)s
        )
        SELECT tipo, chave, titulo, conteudo, metadados, similaridade, relevancia,
               pos_v, pos_c, pos_t, exato,
               CASE
                 WHEN %(qualquer_termo_original)s::tsquery IS NOT NULL THEN
                   ts_headline(
                       'busca.portugues_sem_acento',
                       conteudo,
                       %(qualquer_termo_original)s::tsquery,
                       'StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=38, MinWords=15, FragmentDelimiter= … '
                   )
                 ELSE left(conteudo, 280)
               END AS trecho_destacado
        FROM ranqueados
        ORDER BY relevancia DESC, similaridade DESC
        """
    ).format(filtro=filtro_sql)

    parametros: Dict[str, Any] = {
        "v": vetor,
        "q": consulta,
        "q_sem_acento": sem_acento(consulta),
        "k": k,
        "n": max(CANDIDATOS, k),
        "min_vetor": SIMILARIDADE_MINIMA,
        "min_vetor_com_evidencia": SIMILARIDADE_COM_EVIDENCIA,
        "min_texto": SIMILARIDADE_TEXTO_MINIMA,
        "rrf_k": RRF_K,
        "peso_completo": PESO_TEXTO_COMPLETO,
        "peso_titulo": PESO_TITULO,
        "relaxar_com_filtro": tem_filtro_facetado,
        **params_filtro,
    }
    with conexao_do_pool(url) as conn:
        with conn.cursor() as cur:
            # No cursor, e não na conexão, que volta ao pool: o vetor vai em binário.
            register_vector_info(cur, TypeInfo.fetch(conn, "vector"))
            with conn.transaction():
                # Com filtro por tipo ou metadados, a varredura iterativa (pgvector >= 0.8)
                # continua buscando no índice HNSW até completar os candidatos.
                cur.execute("SET LOCAL hnsw.iterative_scan = strict_order")
                cur.execute("SET LOCAL hnsw.ef_search = 200")
                # Os termos da consulta sem acento, já reduzidos ao radical e sem palavras vazias.
                termos_originais = cur.execute(
                    "SELECT tsvector_to_array(to_tsvector('portuguese', %s))",
                    (sem_acento(consulta),),
                ).fetchone()[0]
                termos_expandidos = cur.execute(
                    "SELECT tsvector_to_array(to_tsvector('portuguese', %s))",
                    (sem_acento(consulta_expandida),),
                ).fetchone()[0]
                # Cobertura usa os termos originais (para não diluir a exigência de metade dos termos
                # com os sinônimos), enquanto o ranking e o highlight consideram também os sinônimos.
                parametros["cobertura"] = consulta_de_cobertura(termos_originais)
                parametros["qualquer_termo"] = consulta_de_cobertura(termos_expandidos, 0)
                # Para ts_headline, os termos sem acento: ele usa a configuração busca.portugues_sem_acento
                # (migração 0032), que tira o acento do texto do documento antes do radical sem mudar o que
                # é exibido. Assim o realce funciona com e sem acento dos dois lados: documentação tem
                # acento, cursos e projetos vêm sem acento da Silver.
                parametros["qualquer_termo_original"] = consulta_de_cobertura(termos_originais, 0)
                linhas = cur.execute(consulta_sql, parametros).fetchall()

    return [
        {
            "tipo": t,
            "chave": ch,
            "titulo": ti,
            "conteudo": c,
            "metadados": m,
            "similaridade": round(float(s), 4),
            "relevancia": round(float(r), 5),
            "fontes": _resumir_fontes(pv, pc, pt, bool(ex)),
            "trecho_destacado": hl or c[:280],
            "expansoes": expansoes,
        }
        for t, ch, ti, c, m, s, r, pv, pc, pt, ex, hl in linhas
    ]


def projetos_semelhantes(chave_projeto: str, k: int = 4) -> List[Dict]:
    """Retorna os k planos de IC (PIBIC) mais parecidos semanticamente em busca.documentos."""
    with conexao_do_pool() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL hnsw.iterative_scan = strict_order")
            linhas = cur.execute(
                """
                WITH alvo AS (
                    SELECT embedding FROM busca.documentos
                    WHERE tipo = 'projeto_pibic' AND chave = %(chave)s
                    LIMIT 1
                )
                SELECT d.chave, d.titulo, d.metadados, 1 - (d.embedding <=> a.embedding) AS similaridade
                FROM busca.documentos d
                CROSS JOIN alvo a
                WHERE d.tipo = 'projeto_pibic' AND d.chave <> %(chave)s
                ORDER BY d.embedding <=> a.embedding
                LIMIT %(k)s
                """,
                {"chave": chave_projeto, "k": k},
            ).fetchall()
    return [
        {
            "chave": ch,
            "titulo": titulo,
            "metadados": meta or {},
            "similaridade": round(float(sim), 4),
        }
        for ch, titulo, meta, sim in linhas
    ]


def cursos_semelhantes(nome_curso: str, k: int = 4) -> List[Dict]:
    """Retorna os k cursos mais parecidos semanticamente em busca.documentos (pgvector)."""
    with conexao_do_pool() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL hnsw.iterative_scan = strict_order")
            linhas = cur.execute(
                """
                WITH alvo AS (
                    SELECT embedding FROM busca.documentos
                    WHERE tipo = 'curso' AND chave = %(curso)s
                    LIMIT 1
                )
                SELECT d.titulo, d.metadados, 1 - (d.embedding <=> a.embedding) AS similaridade
                FROM busca.documentos d
                CROSS JOIN alvo a
                WHERE d.tipo = 'curso' AND d.chave <> %(curso)s
                ORDER BY d.embedding <=> a.embedding
                LIMIT %(k)s
                """,
                {"curso": nome_curso, "k": k},
            ).fetchall()
    return [
        {
            "curso": titulo,
            "metadados": meta or {},
            "similaridade": round(float(sim), 4),
        }
        for titulo, meta, sim in linhas
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
        fontes = ", ".join(r["fontes"])
        print(f"{i}. [{r['tipo']}] {r['titulo']}  (sim={r['similaridade']:.3f} | {fontes})")
        print(f"   {r['conteudo'][:220].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()

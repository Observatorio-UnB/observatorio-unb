"""
Vetorização para busca semântica (pgvector).

Monta um documento de texto por entidade pesquisável, a partir do próprio banco,
e grava o embedding em busca.documentos:

- curso:          uma linha de gold.retencao_cursos_unb, descrita em frase;
- projeto_pibic:  cada plano de IC distinto de silver.pibic_bolsistas (título, ano,
                  curso, linha de pesquisa), sem nome, matrícula ou orientador;
- documentacao:   cada seção dos .md de docs/ (metodologia, qualidade, LGPD...).

É incremental: o embedding só é recalculado quando o texto ou o modelo mudam
(hash_conteudo), e documentos que deixaram de existir na fonte são apagados.
A primeira execução completa leva minutos em CPU (~12,5 mil planos de IC); as
seguintes só vetorizam o que mudou.

Uso:
    python3 src/busca/vetorizar.py
    VETORIZAR_TIPOS=curso,documentacao python3 src/busca/vetorizar.py   # sem os planos de IC (CI)
"""

import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vetorizar")

DOCS_DIR = BASE_DIR / "docs"

# Multilíngue (entende português), 384 dimensões, ~220 MB, roda em CPU via ONNX.
# A dimensão está fixada em busca.documentos.embedding (db/migrations/0005).
MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSAO = 384

# Seções longas da documentação são quebradas em pedaços deste tamanho (caracteres):
# o modelo foi treinado com entradas de até 128 tokens (~500 caracteres em português),
# e texto além disso pesa pouco ou nada no vetor.
TAMANHO_MAX_TRECHO = 500


@dataclass
class Documento:
    tipo: str
    chave: str
    titulo: str
    conteudo: str
    metadados: Dict = field(default_factory=dict)


def nome_do_modelo() -> str:
    return os.environ.get("EMBEDDING_MODEL", MODELO_PADRAO)


def carregar_modelo(nome: str):
    """Carrega o modelo de embedding (baixa na primeira vez para FASTEMBED_CACHE_PATH)."""
    from fastembed import TextEmbedding

    cache = os.environ.get("FASTEMBED_CACHE_PATH", str(BASE_DIR / ".cache" / "fastembed"))
    return TextEmbedding(model_name=nome, cache_dir=cache)


def gerar_embeddings(modelo, textos: List[str]) -> np.ndarray:
    """Embeddings normalizados (norma 1), para que a distância de cosseno seja direta."""
    vetores = np.array(list(modelo.embed(textos, batch_size=64)), dtype=np.float32)
    if vetores.shape[1] != DIMENSAO:
        raise ValueError(
            f"O modelo gera vetores de {vetores.shape[1]} dimensões, mas a coluna é vector({DIMENSAO}). "
            "Trocar de modelo exige uma migração nova."
        )
    return vetores / np.linalg.norm(vetores, axis=1, keepdims=True)


def vetor_literal(vetor: Iterable[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vetor) + "]"


def _fmt(valor, sufixo: str = "") -> str:
    return "sem dado" if valor is None else f"{float(valor):g}{sufixo}"


# O embedding capta palavras, não grandezas: "49,92%" não fica perto de "muita evasão".
# As faixas abaixo dão à busca um vocabulário para os números (limiares fixos, não quartis,
# para que a descrição de um curso não mude quando outro curso muda).
def _faixa_evasao(taxa) -> str:
    if taxa is None:
        return "evasão sem dado"
    taxa = float(taxa)
    if taxa >= 60:
        return "evasão muito alta"
    if taxa >= 45:
        return "evasão alta"
    if taxa >= 30:
        return "evasão moderada"
    return "evasão baixa"


def _faixa_atraso(desvio) -> str:
    if desvio is None:
        return "tempo de formatura sem dado"
    desvio = float(desvio)
    if desvio >= 2:
        return "formatura com muito atraso"
    if desvio >= 0.5:
        return "formatura com algum atraso"
    return "formatura no prazo"


def documentos_de_cursos(conn: psycopg.Connection) -> List[Documento]:
    linhas = conn.execute(
        """
        SELECT curso, categoria_grau, grau_academico, campus, turno, area_conhecimento,
               classificacao_retencao, indice_retencao_critica, taxa_evasao_pct, taxa_formatura_pct,
               total_discentes_registrados, formados_tempo_ideal_pct, semestre_ideal_previsto,
               tempo_medio_real_semestres, desvio_medio_semestres
        FROM gold.retencao_cursos_unb
        """
    ).fetchall()
    docs = []
    for (curso, categoria, grau, campus, turno, area, classe, irc, evasao, formatura,
         total, no_ideal, ideal, tempo_medio, desvio) in linhas:
        # Frase em minúsculas: o tokenizador do modelo lida mal com texto todo em caixa alta.
        conteudo = (
            f"curso de {curso.lower()} ({categoria.lower()}, {grau.lower()}), campus {campus.lower()}, "
            f"turno {turno.lower()}, área de {area.lower()}. "
            f"{classe.lower()}, {_faixa_evasao(evasao)}, {_faixa_atraso(desvio)}. "
            f"índice de retenção crítica {_fmt(irc)}. "
            f"evasão de {_fmt(evasao, '%')} e formatura de {_fmt(formatura, '%')} entre {total} vínculos. "
            f"{_fmt(no_ideal, '%')} dos formados concluem no tempo ideal de {_fmt(ideal)} semestres; "
            f"tempo médio real de {_fmt(tempo_medio)} semestres ({_fmt(desvio)} de atraso médio)."
        )
        docs.append(Documento(
            tipo="curso",
            chave=curso,
            titulo=curso,
            conteudo=conteudo,
            metadados={
                "campus": campus, "turno": turno, "area_conhecimento": area,
                "classificacao_retencao": classe,
                "indice_retencao_critica": float(irc) if irc is not None else None,
                "taxa_evasao_pct": float(evasao) if evasao is not None else None,
                "taxa_formatura_pct": float(formatura) if formatura is not None else None,
            },
        ))
    return docs


def documentos_de_projetos_pibic(conn: psycopg.Connection) -> List[Documento]:
    # Sem matrícula, orientador e perfil social: o que se pesquisa é o tema do plano.
    linhas = conn.execute(
        """
        SELECT titulo_norm, ano, coalesce(curso_pibic_norm, ''), campus, coalesce(linha_pesquisa_norm, ''),
               count(*) AS planos
        FROM silver.pibic_bolsistas
        WHERE coalesce(titulo_norm, '') <> ''
        GROUP BY 1, 2, 3, 4, 5
        """
    ).fetchall()
    docs = []
    for titulo, ano, curso, campus, linha, planos in linhas:
        chave = hashlib.sha1(f"{titulo}|{ano}|{curso}|{campus}|{linha}".encode()).hexdigest()
        contexto = [f"iniciação científica de {ano}"]
        if curso:
            contexto.append(f"curso de {curso.lower()}")
        if linha:
            contexto.append(f"linha {linha.lower()}")
        docs.append(Documento(
            tipo="projeto_pibic",
            chave=chave,
            titulo=titulo.capitalize(),
            conteudo=f"{titulo.lower()}. {', '.join(contexto)}.",
            metadados={"ano": ano, "curso": curso or None, "campus": campus,
                       "linha_pesquisa": linha or None, "planos": planos},
        ))
    return docs


def _trechos(texto: str, limite: int = TAMANHO_MAX_TRECHO) -> List[str]:
    """Quebra um texto em pedaços de até `limite` caracteres, respeitando parágrafos e linhas."""
    pedacos, atual = [], ""
    for bloco in re.split(r"\n\s*\n|\n(?=\|)", texto):
        bloco = bloco.strip()
        if not bloco:
            continue
        while len(bloco) > limite:
            pedacos.append(bloco[:limite])
            bloco = bloco[limite:]
        if atual and len(atual) + len(bloco) + 1 > limite:
            pedacos.append(atual)
            atual = bloco
        else:
            atual = f"{atual}\n{bloco}".strip()
    if atual:
        pedacos.append(atual)
    return pedacos


def documentos_da_documentacao(docs_dir: Path = DOCS_DIR) -> List[Documento]:
    docs = []
    for arquivo in sorted(docs_dir.glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8")
        # Uma seção por título de nível 1 a 3; o que vem antes do primeiro título é a introdução.
        partes = re.split(r"^(#{1,3} .+)$", texto, flags=re.MULTILINE)
        secao, corpo_acumulado = arquivo.stem, [partes[0]]
        secoes = []
        for parte in partes[1:]:
            if re.match(r"^#{1,3} ", parte):
                secoes.append((secao, "".join(corpo_acumulado)))
                secao, corpo_acumulado = parte.lstrip("#").strip(), []
            else:
                corpo_acumulado.append(parte)
        secoes.append((secao, "".join(corpo_acumulado)))

        for i, (titulo_secao, corpo) in enumerate(secoes):
            for j, trecho in enumerate(_trechos(corpo)):
                docs.append(Documento(
                    tipo="documentacao",
                    chave=f"{arquivo.name}#{i}.{j}",
                    titulo=f"{arquivo.name} › {titulo_secao}",
                    conteudo=f"{titulo_secao}\n{trecho}",
                    metadados={"arquivo": f"docs/{arquivo.name}", "secao": titulo_secao},
                ))
    return docs


def _hash(modelo: str, conteudo: str) -> str:
    return hashlib.sha256(f"{modelo}\n{conteudo}".encode("utf-8")).hexdigest()


TIPOS = ("curso", "projeto_pibic", "documentacao")


def tipos_escolhidos() -> List[str]:
    escolhidos = [t.strip() for t in os.environ.get("VETORIZAR_TIPOS", ",".join(TIPOS)).split(",") if t.strip()]
    desconhecidos = set(escolhidos) - set(TIPOS)
    if desconhecidos:
        raise ValueError(f"VETORIZAR_TIPOS tem tipos desconhecidos: {sorted(desconhecidos)}. Use {TIPOS}.")
    return escolhidos


def vetorizar() -> Dict[str, int]:
    """Sincroniza busca.documentos com o banco e a documentação. Devolve documentos por tipo."""
    nome = nome_do_modelo()
    modelo = None
    resumo = {}
    with conectar(autocommit=True) as conn:
        geradores = {
            "curso": lambda: documentos_de_cursos(conn),
            "projeto_pibic": lambda: documentos_de_projetos_pibic(conn),
            "documentacao": documentos_da_documentacao,
        }
        for tipo in tipos_escolhidos():
            gerar = geradores[tipo]
            docs = gerar()
            existentes = dict(conn.execute(
                "SELECT chave, hash_conteudo FROM busca.documentos WHERE tipo = %s", (tipo,)
            ).fetchall())
            novos = [d for d in docs if existentes.get(d.chave) != _hash(nome, d.conteudo)]

            if novos:
                modelo = modelo or carregar_modelo(nome)
                logger.info(f"{tipo}: vetorizando {len(novos):,} de {len(docs):,} documentos...")
                vetores = gerar_embeddings(modelo, [d.conteudo for d in novos])
            else:
                vetores = []

            with conn.transaction():
                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO busca.documentos
                          (tipo, chave, titulo, conteudo, metadados, hash_conteudo, modelo, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                        ON CONFLICT (tipo, chave) DO UPDATE SET
                          titulo = EXCLUDED.titulo, conteudo = EXCLUDED.conteudo,
                          metadados = EXCLUDED.metadados, hash_conteudo = EXCLUDED.hash_conteudo,
                          modelo = EXCLUDED.modelo, embedding = EXCLUDED.embedding, atualizado_em = now()
                        """,
                        [
                            (d.tipo, d.chave, d.titulo, d.conteudo, json.dumps(d.metadados, ensure_ascii=False),
                             _hash(nome, d.conteudo), nome, vetor_literal(v))
                            for d, v in zip(novos, vetores)
                        ],
                    )
                removidos = conn.execute(
                    "DELETE FROM busca.documentos WHERE tipo = %s AND NOT (chave = ANY(%s))",
                    (tipo, [d.chave for d in docs]),
                ).rowcount
            logger.info(
                f"{tipo}: {len(docs):,} documentos ({len(novos):,} vetorizados, "
                f"{len(docs) - len(novos):,} sem mudança, {removidos:,} removidos)."
            )
            resumo[tipo] = len(docs)
        conn.execute("ANALYZE busca.documentos")
    logger.info("=== Vetorização concluída ===")
    return resumo


if __name__ == "__main__":
    vetorizar()

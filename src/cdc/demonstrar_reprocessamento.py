"""
Demonstra a semântica de entrega do fluxo CDC forçando reprocessamentos.

Declarada: no mínimo uma vez no transporte (o offset só é confirmado no Kafka depois da gravação
no lago) e efeito de exatamente uma vez no lago (o MERGE só aplica um evento mais novo, pela
posição no WAL, que a linha do lago). Esta demonstração confere isso com o dado real:

  1. Um lote de mudanças no OLTP: cursos sentinela 990100 a 990149 em silver.cursos, cada um
     com um INSERT e um UPDATE (100 eventos).
  2. Queda antes da confirmação: o consumidor grava o lote no lago e cai sem confirmar o offset.
  3. Retomada: um consumidor novo do mesmo grupo recebe o lote de novo e o aplica outra vez.
  4. Reprocessamento completo: o grupo volta ao primeiro offset e relê os tópicos inteiros.

Depois de cada passo, compara a impressão digital do lago (sha256 de todas as linhas, inclusive
as marcadas como excluídas, sem a coluna _gravado_em). No fim, os sentinelas são excluídos do
banco (mesmo se a demonstração falhar no meio) e a exclusão é aplicada no lago.

Requer o profile cdc no ar e o conector registrado (scripts/cdc.sh registrar).

Uso:
    python3 src/cdc/demonstrar_reprocessamento.py
"""

import hashlib
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.cdc import lago  # noqa: E402
from src.cdc.consumidor import Consumidor  # noqa: E402
from src.db.conexao import conectar  # noqa: E402

SENTINELAS = range(990100, 990150)
EVENTOS_DO_LOTE = 2 * len(SENTINELAS)
PRAZO_S = 60


def impressao_digital(consumidor: Consumidor) -> Tuple[str, int]:
    """sha256 do conteúdo do lago CDC e total de linhas (inclusive as marcadas como excluídas)."""
    digest, total = hashlib.sha256(), 0
    for tabela in consumidor.tabelas.values():
        dados = lago.ler(tabela, com_excluidas=True).drop_columns(["_gravado_em"])
        dados = dados.sort_by([(c, "ascending") for c in tabela.chave])
        digest.update(dados.to_pandas().to_csv(index=False).encode())
        total += len(dados)
    return digest.hexdigest()[:12], total


def sentinelas_no_lago(consumidor: Consumidor) -> int:
    cursos = lago.ler(consumidor.tabelas["observatorio.silver.cursos"]).column("id_curso").to_pylist()
    return sum(1 for c in cursos if c in SENTINELAS)


def mudar_o_oltp() -> None:
    with conectar() as conn:
        for id_curso in SENTINELAS:
            conn.execute(
                """INSERT INTO silver.cursos (id_curso, codigo_sigaa, nome_curso_norm, campus, turno,
                                              grau_academico, categoria_grau, area_conhecimento)
                   VALUES (%s, 'CDC', 'CURSO SENTINELA DO REPROCESSAMENTO', 'DARCY RIBEIRO', 'DIURNO',
                           'BACHARELADO', 'BACHARELADO', 'DEMONSTRACAO')""",
                (id_curso,),
            )
        conn.execute("UPDATE silver.cursos SET turno = 'NOTURNO' WHERE id_curso BETWEEN %s AND %s",
                     (SENTINELAS[0], SENTINELAS[-1]))


def gravar_e_cair() -> int:
    """Lê o lote, grava no lago e fecha sem confirmar o offset. Devolve as mensagens lidas."""
    consumidor = Consumidor()
    lidas, inicio = 0, time.monotonic()
    try:
        while lidas < EVENTOS_DO_LOTE:
            if time.monotonic() - inicio > PRAZO_S:
                raise TimeoutError(f"O lote não chegou em {PRAZO_S} s. O conector está no ar? (scripts/cdc.sh status)")
            lidas += consumidor.rodada(timeout=0.5, confirmar=False)
    finally:
        consumidor.fechar()
    return lidas


def demonstrar() -> None:
    linhas = []

    def registrar(cenario: str, lidas: int, consumidor: Consumidor) -> Dict:
        digest, total = impressao_digital(consumidor)
        linha = {"cenario": cenario, "lidas": lidas, "total": total,
                 "sentinelas": sentinelas_no_lago(consumidor), "digest": digest}
        linhas.append(linha)
        return linha

    try:
        consumidor = Consumidor()
        registrar("estado inicial (tópicos esvaziados)", consumidor.esvaziar(ociosidade_s=3), consumidor)
        consumidor.fechar()

        mudar_o_oltp()
        lidas = gravar_e_cair()
        consumidor = Consumidor()
        apos_lote = registrar("lote gravado, queda antes de confirmar", lidas, consumidor)

        retomada = registrar("retomada: o lote é entregue de novo", consumidor.esvaziar(ociosidade_s=3), consumidor)
        consumidor.fechar()

        consumidor = Consumidor(do_inicio=True)
        completo = registrar("reprocessamento do primeiro offset", consumidor.esvaziar(ociosidade_s=3), consumidor)
        consumidor.fechar()
    finally:
        with conectar() as conn:
            conn.execute("DELETE FROM silver.cursos WHERE id_curso BETWEEN %s AND %s",
                         (SENTINELAS[0], SENTINELAS[-1]))
        consumidor = Consumidor()
        consumidor.esvaziar(ociosidade_s=3)
        consumidor.fechar()

    print(f"\n{'cenário':<42}{'mensagens lidas':>16}{'linhas no lago':>16}{'sentinelas':>12}   impressão digital")
    for l in linhas:
        print(f"{l['cenario']:<42}{l['lidas']:>16,}{l['total']:>16,}{l['sentinelas']:>12}   {l['digest']}")

    redelivery = retomada["lidas"] >= EVENTOS_DO_LOTE
    iguais = apos_lote["digest"] == retomada["digest"] == completo["digest"]
    print(
        f"\nO Kafka entregou o lote {'de novo' if redelivery else 'só uma vez (?)'} depois da queda "
        f"({retomada['lidas']:,} mensagens) e o grupo inteiro outra vez no reprocessamento "
        f"({completo['lidas']:,}).\n"
        f"Lago depois da queda, da retomada e do reprocessamento: "
        f"{'idêntico nos três' if iguais else 'DIFERENTE'} ({apos_lote['digest']}).\n"
        "Transporte no mínimo uma vez; efeito no lago de exatamente uma vez."
    )
    if not (redelivery and iguais):
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("consumidor_cdc").setLevel(logging.WARNING)
    demonstrar()

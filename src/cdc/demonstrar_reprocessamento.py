"""
Demonstra a semântica de entrega do fluxo CDC forçando reprocessamentos.

Declarada: no mínimo uma vez no transporte (o offset só é confirmado no Kafka depois da gravação
no lago) e efeito de exatamente uma vez no lago (o MERGE só aplica um evento mais novo, pela
posição no WAL, que a linha do lago). Esta demonstração confere isso com o dado real:

  1. Um lote de mudanças no OLTP: cursos sentinela 990100 a 990149 em silver.cursos, cada um
     com um INSERT e um UPDATE (100 eventos).
  2. Queda antes da confirmação: o consumidor grava os INSERTs no lago, o UPDATE só é feito
     depois, numa transação própria, e é gravado por outro MERGE; aí o consumidor cai sem
     confirmar o offset. Com o UPDATE noutro lote, ele só vence a linha do lago pelo commit da
     transação (source.sequence[0]), e não pelo desempate dentro do mesmo lote.
  3. Retomada: um consumidor novo do mesmo grupo recebe o lote de novo e o aplica outra vez.
  4. Reprocessamento completo: o grupo volta ao primeiro offset e relê os tópicos inteiros.
  5. Exclusão: os sentinelas são excluídos do banco, e a demonstração espera o DELETE chegar
     ao lago (nenhum sentinela vivo).
  6. Reprocessamento depois da exclusão: o grupo relê os tópicos do primeiro offset, com os
     INSERTs antigos dos sentinelas, e nenhum deles pode ressuscitar.

Depois de cada passo, calcula a impressão digital do lago (sha256 de todas as linhas, inclusive
as marcadas como excluídas e a coluna _gravado_em). Confere que o lote mudou o lago, que os 50
sentinelas chegaram com o valor do UPDATE (turno NOTURNO) e commit posterior ao do INSERT, que
a retomada e o reprocessamento não mudaram nada, nem a hora de gravação de linha nenhuma, e que
o reprocessamento depois da exclusão também não. Se falhar no meio, os sentinelas são excluídos do banco do mesmo jeito.

Requer o profile cdc no ar e o conector registrado (scripts/cdc.sh registrar).

Uso:
    python3 src/cdc/demonstrar_reprocessamento.py
"""

import hashlib
import logging
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.cdc import lago  # noqa: E402
from src.cdc.consumidor import Consumidor, carregar_tabelas  # noqa: E402
from src.db.conexao import conectar  # noqa: E402

logger = logging.getLogger("demonstrar_reprocessamento")

SENTINELAS = range(990100, 990150)
EVENTOS_DO_LOTE = 2 * len(SENTINELAS)
PRAZO_S = 60
TOPICO_CURSOS = "observatorio.silver.cursos"

Tabelas = Dict[str, lago.Tabela]


def impressao_digital(tabelas: Tabelas) -> Tuple[str, int]:
    """sha256 do conteúdo do lago CDC e total de linhas (inclusive as marcadas como excluídas).

    Inclui _gravado_em: como o MERGE só aplica evento estritamente mais novo, uma entrega
    repetida não reescreve linha nenhuma, e a hora de gravação de cada uma não muda.
    """
    digest, total = hashlib.sha256(), 0
    for tabela in tabelas.values():
        dados = lago.ler(tabela, com_excluidas=True)
        dados = dados.sort_by([(c, "ascending") for c in tabela.chave])
        digest.update(dados.to_pandas().to_csv(index=False).encode())
        total += len(dados)
    return digest.hexdigest()[:12], total


def sentinelas(tabelas: Tabelas) -> List[Dict]:
    """Linhas dos cursos sentinela no lago, inclusive as marcadas como excluídas."""
    cursos = lago.ler(tabelas[TOPICO_CURSOS], com_excluidas=True).to_pylist()
    return [r for r in cursos if r["id_curso"] in SENTINELAS]


def sentinelas_vivos(tabelas: Tabelas) -> List[Dict]:
    return [r for r in sentinelas(tabelas) if not r["_deletado"]]


def inserir_sentinelas() -> None:
    with conectar() as conn:
        for id_curso in SENTINELAS:
            conn.execute(
                """INSERT INTO silver.cursos (id_curso, codigo_sigaa, nome_curso_norm, campus, turno,
                                              grau_academico, categoria_grau, area_conhecimento)
                   VALUES (%s, 'CDC', 'CURSO SENTINELA DO REPROCESSAMENTO', 'DARCY RIBEIRO', 'DIURNO',
                           'BACHARELADO', 'BACHARELADO', 'DEMONSTRACAO')""",
                (id_curso,),
            )


def atualizar_sentinelas() -> None:
    with conectar() as conn:
        conn.execute("UPDATE silver.cursos SET turno = 'NOTURNO' WHERE id_curso BETWEEN %s AND %s",
                     (SENTINELAS[0], SENTINELAS[-1]))


def com_turno(tabelas: Tabelas, turno: str) -> List[Dict]:
    return [r for r in sentinelas_vivos(tabelas) if r["turno"] == turno]


def gravar_e_cair(tabelas: Tabelas) -> Tuple[int, int]:
    """Grava os INSERTs no lago, faz o UPDATE, grava-o por outro MERGE e fecha sem confirmar o
    offset. Devolve as mensagens lidas e o maior _commit_lsn dos sentinelas depois dos INSERTs."""
    n = len(SENTINELAS)
    with Consumidor() as consumidor:
        inserir_sentinelas()
        lidas = esperar(consumidor, lambda: len(com_turno(tabelas, "DIURNO")) == n, "O INSERT dos sentinelas",
                        confirmar=False)
        commit_do_insert = max(r["_commit_lsn"] for r in sentinelas_vivos(tabelas))
        atualizar_sentinelas()
        lidas += esperar(consumidor, lambda: len(com_turno(tabelas, "NOTURNO")) == n, "O UPDATE dos sentinelas",
                         confirmar=False)
    return lidas, commit_do_insert


def esperar(consumidor: Consumidor, chegou: Callable[[], bool], o_que: str, confirmar: bool = True) -> int:
    """Consome até `chegou()` valer, com prazo. Devolve as mensagens lidas."""
    lidas, inicio = 0, time.monotonic()
    while not chegou():
        if time.monotonic() - inicio > PRAZO_S:
            raise TimeoutError(f"{o_que} não chegou ao lago em {PRAZO_S} s. O conector está no ar? (scripts/cdc.sh status)")
        lidas += consumidor.rodada(timeout=0.5, confirmar=confirmar)
    return lidas


def excluir_sentinelas(tabelas: Tabelas) -> int:
    """Exclui os sentinelas do banco e espera o DELETE chegar ao lago. Devolve as mensagens lidas.

    Sem a espera, o consumidor poderia parar antes de o evento atravessar o Debezium e o Kafka,
    e os sentinelas ficariam vivos no lago para quem filtra por NOT _deletado.
    """
    with conectar() as conn:
        conn.execute("DELETE FROM silver.cursos WHERE id_curso BETWEEN %s AND %s",
                     (SENTINELAS[0], SENTINELAS[-1]))
    with Consumidor() as consumidor:
        return esperar(consumidor, lambda: not sentinelas_vivos(tabelas), "A exclusão dos sentinelas")


def reprocessar_do_inicio() -> int:
    with Consumidor(do_inicio=True) as consumidor:
        return consumidor.esvaziar(ociosidade_s=3)


def demonstrar() -> None:
    tabelas = carregar_tabelas()
    linhas = []

    def registrar(cenario: str, lidas: int) -> Dict:
        digest, total = impressao_digital(tabelas)
        todos = sentinelas(tabelas)
        vivos = [r for r in todos if not r["_deletado"]]
        linha = {"cenario": cenario, "lidas": lidas, "total": total, "digest": digest,
                 "vivos": len(vivos), "noturnos": sum(r["turno"] == "NOTURNO" for r in vivos),
                 "excluidos": len(todos) - len(vivos)}
        linhas.append(linha)
        return linha

    try:
        with Consumidor() as consumidor:
            inicial = registrar("estado inicial (tópicos esvaziados)", consumidor.esvaziar(ociosidade_s=3))
        lidas, commit_do_insert = gravar_e_cair(tabelas)
        commit_do_update = min(r["_commit_lsn"] for r in sentinelas_vivos(tabelas))
        apos_lote = registrar("lote gravado, queda antes de confirmar", lidas)
        with Consumidor() as consumidor:
            retomada = registrar("retomada: o lote é entregue de novo", consumidor.esvaziar(ociosidade_s=3))
        completo = registrar("reprocessamento do primeiro offset", reprocessar_do_inicio())
    except BaseException:
        # Não deixa sentinela no banco; se a limpeza também falhar, o erro original é o que sobe.
        try:
            excluir_sentinelas(tabelas)
        except Exception:
            logger.exception(f"A exclusão dos sentinelas também falhou: apague do banco os cursos "
                             f"{SENTINELAS[0]} a {SENTINELAS[-1]}.")
        raise
    excluidos = registrar("sentinelas excluídos do banco", excluir_sentinelas(tabelas))
    depois = registrar("reprocessamento depois da exclusão", reprocessar_do_inicio())

    print(f"\n{'cenário':<42}{'mensagens lidas':>16}{'linhas no lago':>16}{'sentinelas vivos':>18}   impressão digital")
    for l in linhas:
        print(f"{l['cenario']:<42}{l['lidas']:>16,}{l['total']:>16,}{l['vivos']:>18}   {l['digest']}")

    n = len(SENTINELAS)
    falhas = []
    if apos_lote["digest"] == inicial["digest"]:
        falhas.append("o lote gravado não mudou o lago")
    if apos_lote["vivos"] != n or apos_lote["noturnos"] != n:
        falhas.append(f"depois do lote, esperados {n} sentinelas vivos com turno NOTURNO; "
                      f"há {apos_lote['vivos']} vivos, {apos_lote['noturnos']} com NOTURNO")
    if commit_do_update <= commit_do_insert:
        falhas.append(f"o UPDATE gravado não tem commit posterior ao do INSERT "
                      f"(_commit_lsn {commit_do_update} <= {commit_do_insert})")
    if retomada["lidas"] < EVENTOS_DO_LOTE:
        falhas.append(f"o Kafka não entregou o lote de novo depois da queda ({retomada['lidas']} mensagens)")
    if not apos_lote["digest"] == retomada["digest"] == completo["digest"]:
        falhas.append("a retomada ou o reprocessamento mudou o lago")
    if excluidos["vivos"] or excluidos["excluidos"] != n:
        falhas.append(f"depois da exclusão, esperados {n} sentinelas marcados como excluídos e nenhum vivo; "
                      f"há {excluidos['excluidos']} marcados e {excluidos['vivos']} vivos")
    if depois["vivos"] or depois["digest"] != excluidos["digest"]:
        falhas.append("o reprocessamento depois da exclusão ressuscitou sentinelas ou mudou o lago")

    print(
        f"\nO Kafka entregou o lote {'de novo' if retomada['lidas'] >= EVENTOS_DO_LOTE else 'só uma vez (?)'} "
        f"depois da queda ({retomada['lidas']:,} mensagens) e o grupo inteiro outra vez em cada "
        f"reprocessamento ({completo['lidas']:,} e {depois['lidas']:,})."
    )
    if falhas:
        print("\nFALHOU:\n" + "\n".join(f"  - {f}" for f in falhas))
        sys.exit(1)
    print(
        f"Lago depois da queda, da retomada e do reprocessamento: idêntico nos três ({apos_lote['digest']}), "
        f"com os {n} sentinelas em turno NOTURNO.\n"
        f"Depois da exclusão e de reler tudo do primeiro offset: nenhum sentinela vivo ({excluidos['digest']}).\n"
        "Transporte no mínimo uma vez; efeito no lago de exatamente uma vez."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("consumidor_cdc").setLevel(logging.WARNING)
    demonstrar()

"""
Demonstra uma mudança atravessando o fluxo: OLTP -> WAL -> Debezium -> Kafka -> lago Delta.

Insere em silver.cursos um curso sentinela (id 990001, que não existe no catálogo), altera e
exclui. A cada passo, consome os tópicos até a mudança aparecer em data/lake/cdc/ e mede quanto
levou desde o commit no PostgreSQL. No fim, o banco volta ao estado de antes: o sentinela é
excluído mesmo se a demonstração falhar no meio. No lago, ele fica como linha marcada
(_deletado = true), invisível para quem filtra por NOT _deletado.

Usa um grupo de consumidores próprio, que começa do fim dos tópicos: rodando junto com o
consumidor de sempre (grupo observatorio-lago), os dois não dividem as partições.

Requer o profile cdc no ar e o conector registrado (scripts/cdc.sh registrar).

Uso:
    python3 src/cdc/demonstrar.py
"""

import logging
import sys
import time
from pathlib import Path
from typing import Callable, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.cdc import lago  # noqa: E402
from src.cdc.consumidor import Consumidor  # noqa: E402
from src.db.conexao import conectar  # noqa: E402

logger = logging.getLogger("demonstrar_cdc")

ID_SENTINELA = 990001
PRAZO_S = 60
GRUPO_DEMONSTRACAO = "observatorio-demonstracao"

PASSOS = (
    (
        "INSERT",
        """INSERT INTO silver.cursos (id_curso, codigo_sigaa, nome_curso_norm, campus, turno, grau_academico,
                                      categoria_grau, area_conhecimento)
           VALUES (%s, 'CDC', 'CURSO SENTINELA DO CDC', 'DARCY RIBEIRO', 'DIURNO', 'BACHARELADO',
                   'BACHARELADO', 'DEMONSTRACAO')""",
        lambda linha: linha is not None and not linha["_deletado"],
    ),
    (
        "UPDATE",
        "UPDATE silver.cursos SET turno = 'NOTURNO', ativo = false WHERE id_curso = %s",
        lambda linha: linha is not None and linha["turno"] == "NOTURNO" and linha["ativo"] is False,
    ),
    (
        "DELETE",
        "DELETE FROM silver.cursos WHERE id_curso = %s",
        lambda linha: linha is not None and linha["_deletado"],
    ),
)


def linha_no_lago(tabela: lago.Tabela) -> Optional[dict]:
    if not lago.DeltaTable.is_deltatable(str(tabela.caminho())):
        return None
    dados = lago.ler(tabela, com_excluidas=True).to_pylist()
    return next((r for r in dados if r["id_curso"] == ID_SENTINELA), None)


def esperar(consumidor: Consumidor, tabela: lago.Tabela, chegou: Callable[[Optional[dict]], bool]) -> dict:
    inicio = time.monotonic()
    while time.monotonic() - inicio < PRAZO_S:
        consumidor.rodada(timeout=0.2)
        linha = linha_no_lago(tabela)
        if chegou(linha):
            return linha
    raise TimeoutError(f"A mudança não chegou ao lago em {PRAZO_S} s. O conector está no ar? (scripts/cdc.sh status)")


def demonstrar() -> None:
    consumidor = Consumidor(grupo=GRUPO_DEMONSTRACAO, sem_offset="latest")
    tabela = consumidor.tabelas["observatorio.silver.cursos"]
    try:
        pendentes = consumidor.esvaziar(ociosidade_s=3)
        if pendentes:
            print(f"(aplicadas {pendentes:,} mensagens que já estavam nos tópicos)")
        print(f"\nCurso sentinela {ID_SENTINELA} em silver.cursos -> {tabela.caminho().relative_to(BASE_DIR)}\n")
        print(f"{'passo':<8}{'latência':>10}   estado no lago")
        for nome, comando, chegou in PASSOS:
            with conectar() as conn:
                conn.execute(comando, (ID_SENTINELA,))
            commit = time.monotonic()
            linha = esperar(consumidor, tabela, chegou)
            estado = f"turno={linha['turno']} ativo={linha['ativo']} _deletado={linha['_deletado']} " \
                     f"_commit_lsn={linha['_commit_lsn']}"
            print(f"{nome:<8}{time.monotonic() - commit:>9.2f}s   {estado}")
        print("\nA linha excluída fica no lago marcada (_deletado=true); quem lê filtra por NOT _deletado.")
    finally:
        with conectar() as conn:
            conn.execute("DELETE FROM silver.cursos WHERE id_curso = %s", (ID_SENTINELA,))
        consumidor.fechar()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    demonstrar()

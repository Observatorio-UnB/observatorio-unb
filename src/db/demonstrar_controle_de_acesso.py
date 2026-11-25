"""
Demonstra o controle de acesso por linha e por coluna (migração 0030) e mede o custo da política.

Tudo numa transação desfeita no fim: cria três usuários de exemplo no papel secretaria_campus, lota
cada um em campi diferentes e mostra, como cada um (SET ROLE):

  - linha: quantos vínculos vê, por campus, contra o total que o dono do banco vê;
  - coluna: ler id_discente é negado; as demais colunas, não;
  - atalhos fechados: partição direta, silver.discentes, lotação dos outros e escrita;
  - custo: a mediana de 15 contagens com a política, contra a mesma contagem filtrada à mão pelo dono.

Não deixa nada no banco: os papéis de exemplo e a lotação somem no ROLLBACK.

Uso:
    python3 src/db/demonstrar_controle_de_acesso.py
"""

import statistics
import sys
import time
from pathlib import Path
from typing import Callable, List, Tuple

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

FCTE = "FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)"
FCTS = "FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)"
FUP = "FACULDADE DE PLANALTINA (FUP)"

USUARIOS = {
    "demo_secretaria_fcte": [FCTE],
    "demo_secretaria_fcts_fup": [FCTS, FUP],
    "demo_sem_lotacao": [],
}

POR_CAMPUS = """
    SELECT c.campus, count(*) FROM silver.movimentacoes_vinculos v
    JOIN silver.cursos c USING (id_curso) GROUP BY 1 ORDER BY 1
"""

# Tentativas que o papel não pode fazer, e o que cada uma mostra.
NEGADAS: List[Tuple[str, str]] = [
    ("coluna id_discente", "SELECT id_discente FROM silver.movimentacoes_vinculos LIMIT 1"),
    ("partição direta", "SELECT count(*) FROM silver.movimentacoes_p2016_2020"),
    ("silver.discentes", "SELECT count(*) FROM silver.discentes"),
    ("escrita no vínculo", "UPDATE silver.movimentacoes_vinculos SET status_aluno = 'X' WHERE false"),
    ("gold sem papel de leitura", "SELECT count(*) FROM gold.fato_retencao_curso"),
]


def mediana_ms(executar: Callable[[], object], vezes: int = 15) -> float:
    tempos = []
    for _ in range(vezes):
        inicio = time.perf_counter()
        executar()
        tempos.append((time.perf_counter() - inicio) * 1000)
    return statistics.median(tempos)


def negada(conn: psycopg.Connection, sql: str) -> bool:
    try:
        with conn.transaction():
            conn.execute(sql).fetchall() if sql.lstrip().upper().startswith("SELECT") else conn.execute(sql)
    except psycopg.errors.InsufficientPrivilege:
        return True
    return False


def main() -> int:
    with conectar(autocommit=True) as conn:
        conn.execute("BEGIN")
        try:
            total = dict(conn.execute(POR_CAMPUS).fetchall())
            print(f"Dono do banco: {sum(total.values()):,} vínculos em {len(total)} campi.\n".replace(",", "."))

            for usuario, campi in USUARIOS.items():
                conn.execute(f'CREATE ROLE "{usuario}" NOLOGIN IN ROLE secretaria_campus')
                for campus in campi:
                    conn.execute("INSERT INTO acesso.lotacao_campus (usuario, campus) VALUES (%s, %s)",
                                 (usuario, campus))

            print("| Usuário | Lotação | Vínculos vistos | Esperado (dono, mesmos campi) |")
            print("|---|---|---|---|")
            for usuario, campi in USUARIOS.items():
                conn.execute(f'SET ROLE "{usuario}"')
                visto = dict(conn.execute(POR_CAMPUS).fetchall())
                lotacao_vista = [r[0] for r in conn.execute("SELECT campus FROM acesso.lotacao_campus").fetchall()]
                conn.execute("RESET ROLE")
                esperado = sum(total.get(c, 0) for c in campi)
                assert sum(visto.values()) == esperado and set(visto) == set(campi), (usuario, visto)
                assert sorted(lotacao_vista) == sorted(campi), "lotação de outro usuário visível"
                print(f"| {usuario} | {', '.join(campi) or '(nenhuma)'} | {sum(visto.values())} | {esperado} |")

            print("\n| Tentativa (como demo_secretaria_fcte) | Resultado |")
            print("|---|---|")
            conn.execute('SET ROLE "demo_secretaria_fcte"')
            for descricao, sql in NEGADAS:
                print(f"| {descricao} | {'negada' if negada(conn, sql) else 'PERMITIDA'} |")
            colunas_ok = conn.execute(
                "SELECT id_vinculo, id_curso, ano_ingresso, tipo_saida_grupo FROM silver.movimentacoes_vinculos LIMIT 1"
            ).fetchone() is not None
            print(f"| demais colunas do vínculo | {'permitidas' if colunas_ok else 'NEGADAS'} |")

            com_politica = mediana_ms(lambda: conn.execute(
                "SELECT count(*) FROM silver.movimentacoes_vinculos").fetchone())
            conn.execute("RESET ROLE")
            sem_politica = mediana_ms(lambda: conn.execute(
                "SELECT count(*) FROM silver.movimentacoes_vinculos v JOIN silver.cursos c USING (id_curso) "
                "WHERE c.campus = %s", (FCTE,)).fetchone())
            print(f"\nContagem dos vínculos da FCTE, mediana de 15: {com_politica:.1f} ms pela política (RLS) "
                  f"contra {sem_politica:.1f} ms com o filtro escrito à mão pelo dono.")
        finally:
            conn.execute("ROLLBACK")
    print("\nTransação desfeita: papéis e lotação de exemplo removidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

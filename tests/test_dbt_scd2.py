"""
Prova que a dim_curso do dbt guarda histórico (SCD tipo 2, ADR 0028) em vez de sobrescrever.

Copia as tabelas da Silver 3NF que o dbt lê para o esquema silver_scd e roda o `dbt build` sobre ela,
com as camadas em esquemas próprios (scd_dbt_*). Depois reclassifica um curso na cópia (muda a área
de conhecimento) e roda o build de novo, com --full-refresh, como no Dagster. A versão antiga tem de
continuar lá, fechada, e o fato e o painel têm de passar para a versão nova. Nada toca a silver nem
as camadas de verdade, e tudo é apagado no fim.

Pulados sem banco no ar, sem silver carregada ou sem o dbt instalado (pip install -r
requirements-dbt.txt; ou DBT=/caminho/do/dbt).

Uso:
    python3 -m unittest tests/test_dbt_scd2.py
"""

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Dict

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.povoar_silver_3nf import silver_carregada  # noqa: E402

ESQUEMA = "silver_scd"
PREFIXO = "scd_"
TABELAS = ("cursos", "estruturas_curriculares", "movimentacoes_vinculos")
CAMADAS = ("dbt_staging", "dbt_intermediate", "dbt_marts", "dbt_snapshots")
TARGET = "target_scd"
CURSO = "MATEMATICA"
AREA_NOVA = "AREA RECLASSIFICADA NO TESTE"

SQL_VERSOES = f"""
    SELECT sk_curso, area_conhecimento, vigente_de, vigente_ate, is_atual
    FROM {PREFIXO}dbt_marts.dim_curso WHERE nome_curso = %s ORDER BY vigente_de
"""


def _dbt() -> str:
    """O dbt de DBT, do PATH ou do .venv; vazio se não houver."""
    candidatos = (os.environ.get("DBT"), "dbt", str(BASE_DIR / ".venv" / "bin" / "dbt"))
    return next((shutil.which(c) for c in candidatos if c and shutil.which(c)), "")


class TestDimCursoScd2NoDbt(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dbt_exe = _dbt()
        if not cls.dbt_exe:
            raise unittest.SkipTest("dbt não instalado: pip install -r requirements-dbt.txt")
        try:
            cls.conn = conectar(autocommit=True, connect_timeout=3)
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        if not silver_carregada(cls.conn):
            cls.conn.close()
            raise unittest.SkipTest("Silver não carregada: rode scripts/rodar_pipeline.sh.")
        cls.apagar_esquemas()
        cls.conn.execute(f"CREATE SCHEMA {ESQUEMA}")
        for tabela in TABELAS:
            cls.conn.execute(f"CREATE TABLE {ESQUEMA}.{tabela} AS SELECT * FROM silver.{tabela}")

    @classmethod
    def tearDownClass(cls):
        cls.apagar_esquemas()
        cls.conn.close()
        shutil.rmtree(BASE_DIR / "transform" / TARGET, ignore_errors=True)

    @classmethod
    def apagar_esquemas(cls) -> None:
        for esquema in (ESQUEMA, *(PREFIXO + camada for camada in CAMADAS)):
            cls.conn.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")

    def build(self) -> Dict[str, str]:
        """`dbt build --full-refresh` sobre a cópia; devolve o status de cada nó. A reconciliação com
        a gold fica de fora: a gold não foi reclassificada junto."""
        resultados = BASE_DIR / "transform" / TARGET / "run_results.json"
        resultados.unlink(missing_ok=True)
        variaveis = json.dumps({"esquema_silver": ESQUEMA, "prefixo_esquema": PREFIXO})
        execucao = subprocess.run(
            ["bash", "scripts/dbt.sh", "build", "--full-refresh", "--exclude", "reconcilia_fato_retencao_com_a_gold",
             "--vars", variaveis, "--target-path", TARGET],
            cwd=BASE_DIR, env={**os.environ, "DBT": self.dbt_exe}, capture_output=True, text=True, timeout=600,
        )
        if not resultados.exists():
            self.fail(f"dbt build não terminou (código {execucao.returncode}):\n"
                      f"{(execucao.stdout + execucao.stderr)[-2000:]}")
        status = {r["unique_id"].split(".")[2]: r["status"] for r in json.loads(resultados.read_text())["results"]}
        problemas = {no: s for no, s in status.items() if s in ("fail", "error", "skipped")}
        self.assertEqual(problemas, {}, (execucao.stdout + execucao.stderr)[-2000:])
        return status

    def versoes(self, curso: str = CURSO):
        return self.conn.execute(SQL_VERSOES, (curso,)).fetchall()

    def test_reclassificacao_abre_versao_sem_apagar_a_anterior(self):
        # 1. Primeira execução: uma versão por curso, todas atuais, desde 1962.
        status = self.build()
        self.assertEqual(status.get("snap_atributos_curso"), "success")
        [(sk_antiga, area_antiga, vigente_de, vigente_ate, atual)] = self.versoes()
        self.assertEqual(vigente_de.isoformat(), "1962-04-21T00:00:00")
        self.assertIsNone(vigente_ate)
        self.assertTrue(atual)
        self.assertNotEqual(area_antiga, AREA_NOVA)
        cursos, linhas = self.conn.execute(
            f"SELECT count(DISTINCT nome_curso), count(*) FROM {PREFIXO}dbt_marts.dim_curso").fetchone()
        self.assertEqual(cursos, linhas)

        # 2. Reexecução sem mudança na origem: nenhuma versão nova, mesma chave.
        self.build()
        self.assertEqual(self.versoes(), [(sk_antiga, area_antiga, vigente_de, None, True)])

        # 3. Reclassificação na origem: a versão antiga fecha e uma nova abre.
        alteradas = self.conn.execute(
            f"UPDATE {ESQUEMA}.cursos SET area_conhecimento = %s WHERE nome_curso_norm = %s", (AREA_NOVA, CURSO),
        ).rowcount
        self.assertGreater(alteradas, 0, f"{CURSO} não está na silver")
        self.build()

        antiga, nova = self.versoes()
        self.assertEqual(antiga[:3], (sk_antiga, area_antiga, vigente_de))
        self.assertFalse(antiga[4])
        self.assertEqual(antiga[3], nova[2], "a versão antiga termina onde a nova começa")
        self.assertEqual((nova[1], nova[3], nova[4]), (AREA_NOVA, None, True))
        self.assertNotEqual(nova[0], sk_antiga)

        # 4. O fato e o painel passam para a versão nova, e o curso aparece uma vez só.
        [(sk_fato,)] = self.conn.execute(
            f"SELECT f.sk_curso FROM {PREFIXO}dbt_marts.fct_retencao_curso f "
            f"JOIN {PREFIXO}dbt_marts.dim_curso c USING (sk_curso) WHERE c.nome_curso = %s", (CURSO,),
        ).fetchall()
        self.assertEqual(sk_fato, nova[0])
        self.assertEqual(
            self.conn.execute(f"SELECT area_conhecimento FROM {PREFIXO}dbt_marts.painel_cursos_criticos "
                              f"WHERE nome_curso = %s", (CURSO,)).fetchall(),
            [(AREA_NOVA,)],
        )


if __name__ == "__main__":
    unittest.main()

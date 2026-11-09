"""
Prova que os testes de dados do dbt (transform/) pegam o dado ruim: um caso por tipo.

Copia as tabelas da Silver 3NF que o dbt lê para o esquema silver_injetado, estraga a cópia de um
jeito por caso e roda o `dbt build` sobre ela, com as camadas em esquemas próprios (inj_dbt_*).
Nada toca a silver nem as camadas de verdade, e tudo é apagado no fim. Cada caso exige que um teste
específico falhe (ou que o build do modelo pare, no caso do contrato de esquema). A base sem
injeção tem de passar inteira: é ela que mostra que a falha vem do dado estragado.

A reconciliação com a gold fica de fora: a gold não foi estragada junto, e ela acusaria todos os casos.

Pulados sem banco no ar, sem silver carregada ou sem o dbt instalado (pip install -r
requirements-dbt.txt; ou DBT=/caminho/do/dbt).

Uso:
    python3 -m unittest tests/test_dbt_dado_ruim.py
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

ESQUEMA = "silver_injetado"
PREFIXO = "inj_"
TABELAS = ("cursos", "estruturas_curriculares", "movimentacoes_vinculos")
TARGET = "target_injecao"
MOV = f"{ESQUEMA}.movimentacoes_vinculos"
EST = f"{ESQUEMA}.estruturas_curriculares"

# caso -> (comandos que estragam a cópia, nome do nó do dbt que tem de falhar)
CASOS = {
    "esquema: coluna muda de tipo na fonte": (
        [f"ALTER TABLE {MOV} ALTER COLUMN semestres_permanencia_valida TYPE numeric"],
        "stg_vinculos",
    ),
    "volume: metade dos vínculos não veio": (
        [f"DELETE FROM {MOV} WHERE id_vinculo % 2 = 0"],
        "volume_entre_stg_vinculos_300000__100000",
    ),
    "unicidade: vínculo duplicado": (
        [f"INSERT INTO {MOV} SELECT * FROM {MOV} WHERE id_vinculo = (SELECT min(id_vinculo) FROM {MOV})"],
        "unique_stg_vinculos_id_vinculo",
    ),
    "integridade: vínculo aponta para matriz inexistente": (
        [f"UPDATE {MOV} SET id_estrutura = -1 WHERE id_vinculo IN (SELECT id_vinculo FROM {MOV} LIMIT 3)"],
        "relationships_stg_vinculos_id_estrutura__id_estrutura__ref_stg_estruturas_curriculares_",
    ),
    "distribuição: salto de série (coorte de 2013 pela metade)": (
        [f"DELETE FROM {MOV} WHERE ano_ingresso = 2013 AND id_vinculo % 2 = 0"],
        "distribuicao_salto_de_serie_entre_coortes",
    ),
    "distribuição: evasão de 2012 virou OUTROS": (
        [f"UPDATE {MOV} SET tipo_saida_grupo = 'OUTROS' WHERE tipo_saida_grupo = 'EVASAO' AND ano_ingresso = 2012"],
        "distribuicao_desfechos_por_coorte",
    ),
    "distribuição: MEDICINA some da coorte de 2014": (
        [f"DELETE FROM {MOV} WHERE ano_ingresso = 2014 AND id_estrutura = "
         f"(SELECT id_estrutura FROM {EST} WHERE nome_curso_canonico = 'MEDICINA')"],
        "distribuicao_curso_que_some",
    ),
    "domínio: permanência negativa": (
        [f"UPDATE {MOV} SET semestres_permanencia_valida = -3 "
         f"WHERE id_vinculo IN (SELECT id_vinculo FROM {MOV} WHERE semestres_permanencia_valida IS NOT NULL LIMIT 5)"],
        "entre_stg_vinculos_semestres_permanencia_valida__35__1",
    ),
    "domínio: saída antes do ingresso com período publicado": (
        [f"UPDATE {MOV} SET ano_saida = ano_ingresso - 2 WHERE id_vinculo IN "
         f"(SELECT id_vinculo FROM {MOV} WHERE NOT periodo_saida_estimado AND ano_saida IS NOT NULL LIMIT 3)"],
        "dominio_saida_antes_do_ingresso",
    ),
    "domínio: prazo ideal zerado na matriz": (
        [f"UPDATE {EST} SET semestre_ideal = 0 WHERE id_estrutura = (SELECT min(id_estrutura) FROM {EST})"],
        "entre_stg_estruturas_curriculares_semestre_ideal__16__4",
    ),
}

# Casos em que um teste do staging pega o erro antes, e o `dbt build` pula o fato e os testes dele.
# Para provar o teste do fato isolado, os modelos são construídos com `dbt run` (sem testes) e só
# o teste esperado roda depois.
CASOS_ISOLADOS = {
    "distribuição: formados contados como evadidos (mediana da evasão por curso)": (
        [f"UPDATE {MOV} SET tipo_saida_grupo = 'EVASAO' WHERE tipo_saida_grupo = 'FORMATURA'"],
        "distribuicao_mediana_evasao_por_curso",
    ),
}


def _dbt() -> str:
    """O dbt de DBT, do PATH ou do .venv; vazio se não houver."""
    candidatos = (os.environ.get("DBT"), "dbt", str(BASE_DIR / ".venv" / "bin" / "dbt"))
    return next((shutil.which(c) for c in candidatos if c and shutil.which(c)), "")


class TestDadoRuim(unittest.TestCase):

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
        # O snapshot da dim_curso sobrevive ao --full-refresh: um resto de execução anterior começaria
        # o histórico com versões de outra cópia.
        cls.conn.execute(f"DROP SCHEMA IF EXISTS {PREFIXO}dbt_snapshots CASCADE")

    @classmethod
    def tearDownClass(cls):
        for esquema in (ESQUEMA, f"{PREFIXO}dbt_staging", f"{PREFIXO}dbt_intermediate", f"{PREFIXO}dbt_marts",
                        f"{PREFIXO}dbt_snapshots"):
            cls.conn.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")
        cls.conn.close()
        shutil.rmtree(BASE_DIR / "transform" / TARGET, ignore_errors=True)

    def copiar_silver(self) -> None:
        """Recria silver_injetado como cópia simples (sem chaves nem restrições) da silver."""
        self.conn.execute(f"DROP SCHEMA IF EXISTS {ESQUEMA} CASCADE")
        self.conn.execute(f"CREATE SCHEMA {ESQUEMA}")
        for tabela in TABELAS:
            self.conn.execute(f"CREATE TABLE {ESQUEMA}.{tabela} AS SELECT * FROM silver.{tabela}")

    def dbt(self, *argumentos: str) -> Dict[str, str]:
        """Roda o dbt sobre a cópia; devolve o status de cada nó (pass, fail, warn, error, skipped).

        O run_results.json é apagado antes: se o dbt morrer sem gravar um novo (erro de compilação ou
        de conexão), o teste falha aqui, e não lê o resultado do caso anterior. Código 1 é o dbt
        acusando teste reprovado, que é o esperado nos casos de injeção; 2 ou mais é o dbt quebrado.
        """
        resultados = BASE_DIR / "transform" / TARGET / "run_results.json"
        resultados.unlink(missing_ok=True)
        variaveis = json.dumps({"esquema_silver": ESQUEMA, "prefixo_esquema": PREFIXO})
        execucao = subprocess.run(
            ["bash", "scripts/dbt.sh", *argumentos, "--vars", variaveis, "--target-path", TARGET],
            cwd=BASE_DIR, env={**os.environ, "DBT": self.dbt_exe}, capture_output=True, text=True, timeout=600,
        )
        if execucao.returncode >= 2 or not resultados.exists():
            self.fail(f"dbt {' '.join(argumentos)} não terminou (código {execucao.returncode}):\n"
                      f"{(execucao.stdout + execucao.stderr)[-2000:]}")
        return {r["unique_id"].split(".")[2]: r["status"] for r in json.loads(resultados.read_text())["results"]}

    def rodar_dbt(self) -> Dict[str, str]:
        return self.dbt("build", "--full-refresh", "--exclude", "reconcilia_fato_retencao_com_a_gold")

    def estragar(self, comandos) -> None:
        """Estraga a cópia. Comando de dados que não afeta nenhuma linha (o dado mudou e o caso ficou
        sem alvo, ex.: MEDICINA sem ingressantes em 2014) falha aqui, com o comando na mensagem."""
        self.copiar_silver()
        for comando in comandos:
            linhas = self.conn.execute(comando).rowcount
            if comando.split()[0] in ("UPDATE", "DELETE", "INSERT"):
                self.assertGreater(linhas, 0, f"A injeção não afetou nenhuma linha: {comando}")

    def test_01_base_sem_injecao_passa(self):
        self.copiar_silver()
        status = self.rodar_dbt()
        problemas = {no: s for no, s in status.items() if s in ("fail", "error", "skipped")}
        self.assertEqual(problemas, {})

    def test_02_cada_dado_ruim_derruba_o_teste_certo(self):
        for caso, (comandos, no_esperado) in CASOS.items():
            with self.subTest(caso=caso):
                self.estragar(comandos)
                status = self.rodar_dbt()
                self.assertIn(status.get(no_esperado), ("fail", "error"),
                              f"{no_esperado} deveria falhar; status: {status.get(no_esperado)}")

    def test_03_teste_do_fato_pega_o_erro_sozinho(self):
        for caso, (comandos, no_esperado) in CASOS_ISOLADOS.items():
            with self.subTest(caso=caso):
                self.estragar(comandos)
                self.dbt("run", "--full-refresh")
                status = self.dbt("test", "--select", no_esperado)
                self.assertEqual(status.get(no_esperado), "fail")


if __name__ == "__main__":
    unittest.main()

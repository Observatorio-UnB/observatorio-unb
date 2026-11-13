"""
Testes unitários do chat sem banco e sem Ollama: validação do SQL e o laço do agente com o modelo simulado.

Uso:
    python3 -m unittest tests/test_unit_chat.py
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.chat.agente import MAX_ITERACOES, conversar  # noqa: E402
from src.chat.ferramentas import SqlRecusado, validar_sql  # noqa: E402


class TestValidarSql(unittest.TestCase):

    def test_aceita_select_e_with(self):
        self.assertEqual(validar_sql("SELECT 1;"), "SELECT 1")
        self.assertTrue(validar_sql("with a as (select 1) select * from a"))

    def test_recusa_escrita_e_varios_comandos(self):
        for sql in ["DROP TABLE gold.dim_curso", "DELETE FROM gold.dim_curso", "SELECT 1; DROP TABLE x",
                    "UPDATE gold.dim_curso SET a = 1", ""]:
            with self.assertRaises(SqlRecusado, msg=sql):
                validar_sql(sql)

    def test_recusa_camadas_com_dado_pessoal(self):
        for sql in ["SELECT * FROM silver.discentes", "select * from BRONZE.x",
                    "SELECT * FROM dbt_staging.stg_vinculos", "SELECT * FROM pg_catalog.pg_roles"]:
            with self.assertRaises(SqlRecusado, msg=sql):
                validar_sql(sql)


class TestAgente(unittest.TestCase):

    def test_chama_ferramenta_e_devolve_resposta_final(self):
        respostas = iter([
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "consultar_sql", "arguments": {"sql": "SELECT 1"}}}]},
            {"role": "assistant", "content": "Resultado: 1"},
        ])
        chamadas = []
        r = conversar([], "quanto?", llm=lambda m: next(respostas),
                      ferramenta=lambda n, a: chamadas.append((n, a)) or "ok", esquema=lambda: "")
        self.assertEqual(r["resposta"], "Resultado: 1")
        self.assertEqual(r["consultas"], ["SELECT 1"])
        self.assertEqual(chamadas, [("consultar_sql", {"sql": "SELECT 1"})])

    def test_laco_de_ferramentas_tem_limite(self):
        sempre = {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "descrever_esquema", "arguments": "{}"}}]}
        n = []
        r = conversar([], "?", llm=lambda m: n.append(1) or sempre, ferramenta=lambda *_: "x",
                      esquema=lambda: "")
        self.assertEqual(len(n), MAX_ITERACOES)
        self.assertIn("reformule", r["resposta"])

    def test_esquema_vai_no_prompt_de_sistema(self):
        h = []
        conversar(h, "?", llm=lambda m: {"role": "assistant", "content": "a"}, esquema=lambda: "gold.tabela_x")
        self.assertIn("gold.tabela_x", h[0]["content"])

    def test_sql_escrito_no_texto_vira_chamada_da_ferramenta(self):
        respostas = iter([
            {"role": "assistant", "content": "Vou consultar:\n```sql\nSELECT count(*) FROM gold.dim_curso;\n```"},
            {"role": "assistant", "content": "São 112."},
        ])
        chamadas = []
        r = conversar([], "quantos?", llm=lambda m: next(respostas), esquema=lambda: "",
                      ferramenta=lambda n, a: chamadas.append((n, a)) or "112")
        self.assertEqual(r["resposta"], "São 112.")
        self.assertEqual(chamadas, [("consultar_sql", {"sql": "SELECT count(*) FROM gold.dim_curso;"})])
        self.assertEqual(r["consultas"], ["SELECT count(*) FROM gold.dim_curso;"])

    def test_historico_mantem_contexto_entre_perguntas(self):
        h = []
        conversar(h, "um", llm=lambda m: {"role": "assistant", "content": "a"}, esquema=lambda: "")
        conversar(h, "dois", llm=lambda m: {"role": "assistant", "content": "b"}, esquema=lambda: "")
        self.assertEqual([m["role"] for m in h], ["system", "user", "assistant", "user", "assistant"])


if __name__ == "__main__":
    unittest.main()

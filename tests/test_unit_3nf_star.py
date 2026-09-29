"""
Testes unitários da carga 3NF / Star Schema e da sincronização com o Supabase (sem PostgreSQL).

A conexão é substituída por um dublê que só registra o SQL executado: conferem a ordem das
etapas, o que é esvaziado e o SQL de mescla gerado para o Supabase.

Uso:
    python3 -m unittest tests/test_unit_3nf_star.py
"""

import re
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import povoar_dimensional as dimensional  # noqa: E402
from src.db import povoar_silver_3nf as silver  # noqa: E402
from src.db.sincronizar_supabase import SINCRONIAS, Sincronia, montar_insercao  # noqa: E402
from src.pipeline.build_gold import ANOS_MATURACAO_COORTE  # noqa: E402


class ConexaoFalsa:
    """Registra (sql, parâmetros) e responde 0 a qualquer consulta."""

    def __init__(self):
        self.executados = []

    def execute(self, sql, params=None):
        self.executados.append((" ".join(sql.split()), params))
        return self

    def fetchone(self):
        return (0,)

    def sqls(self):
        return [sql for sql, _ in self.executados]


class TestPovoamento(unittest.TestCase):

    def test_silver_esvazia_as_tabelas_3nf_antes_de_inserir(self):
        conn = ConexaoFalsa()
        silver.povoar_silver_3nf(conn)
        sqls = conn.sqls()
        self.assertEqual(sqls[0], f"TRUNCATE {', '.join(silver.TABELAS_3NF)} RESTART IDENTITY")
        inserts = [s for s in sqls if s.startswith("INSERT INTO")]
        self.assertEqual([s.split()[2] for s in inserts], list(silver.TABELAS_3NF))

    def test_gold_preserva_dimensoes_e_recria_fatos(self):
        conn = ConexaoFalsa()
        contagens = dimensional.povoar_gold_dimensional(conn)
        sqls = conn.sqls()
        truncates = [s for s in sqls if s.startswith("TRUNCATE")]
        self.assertEqual(truncates, [f"TRUNCATE {', '.join(dimensional.FATOS)} RESTART IDENTITY"])
        for dim in dimensional.DIMENSOES:
            self.assertNotIn(dim, truncates[0])
        # Dimensões antes do TRUNCATE (upsert), fatos depois.
        corte = sqls.index(truncates[0])
        alvos = [re.search(r"INSERT INTO (\S+)", s).group(1) for s in sqls if "INSERT INTO" in s]
        self.assertEqual(alvos, list(dimensional.TABELAS_GOLD))
        self.assertTrue(all("ON CONFLICT" in s for s in sqls[:corte]))
        self.assertFalse(any("ON CONFLICT" in s for s in sqls[corte:]))
        self.assertEqual(set(contagens), set(dimensional.TABELAS_GOLD))

    def test_fato_retencao_usa_o_corte_de_maturacao_do_pipeline(self):
        conn = ConexaoFalsa()
        dimensional.povoar_gold_dimensional(conn)
        params = [p for s, p in conn.executados if s.startswith("WITH corte")]
        self.assertEqual(params, [{"anos_maturacao": ANOS_MATURACAO_COORTE}])

    def test_fatos_so_aceitam_grupos_com_5_ou_mais(self):
        self.assertIn("HAVING count(*) >= 5", dimensional.SQL_FATO_RETENCAO)
        self.assertIn("HAVING count(*) >= 5", dimensional.SQL_FATO_PIBIC_PERFIL)


class TestSincronizacao(unittest.TestCase):
    S = Sincronia("gold.x", ["curso"])
    COLUNAS = ["curso", "total", "taxa"]

    def montar(self, somente_inserir=False, carimbos=(), s=S):
        return " ".join(montar_insercao(s, self.COLUNAS, "SELECT * FROM tmp", somente_inserir, list(carimbos)).split())

    def test_linha_nova_entra_e_linha_que_mudou_e_atualizada(self):
        sql = self.montar()
        self.assertIn("INSERT INTO gold.x AS t (curso, total, taxa) SELECT * FROM tmp", sql)
        self.assertIn("ON CONFLICT (curso) DO UPDATE SET total = EXCLUDED.total, taxa = EXCLUDED.taxa", sql)
        # Linha igual não é reescrita.
        self.assertIn("WHERE (t.total, t.taxa) IS DISTINCT FROM (EXCLUDED.total, EXCLUDED.taxa)", sql)
        self.assertTrue(sql.endswith("RETURNING (xmax = 0)"))

    def test_somente_inserir_nao_toca_linhas_existentes(self):
        sql = self.montar(somente_inserir=True)
        self.assertIn("ON CONFLICT (curso) DO NOTHING", sql)
        self.assertNotIn("UPDATE", sql)

    def test_tabela_so_com_chave_nao_atualiza(self):
        s = Sincronia("gold.x", ["curso", "total", "taxa"])
        self.assertIn("DO NOTHING", self.montar(s=s))

    def test_carimbo_e_renovado_mas_nao_comparado(self):
        sql = self.montar(carimbos=["atualizado_em"])
        self.assertIn("atualizado_em = now()", sql)
        self.assertNotIn("t.atualizado_em", sql)

    def test_constraint_nomeada_vira_alvo_do_conflito(self):
        s = Sincronia("gold.x", ["curso"], conflito="ON CONSTRAINT uk_x")
        self.assertIn("ON CONFLICT ON CONSTRAINT uk_x DO UPDATE", self.montar(s=s))

    def test_dimensoes_chegam_antes_dos_fatos_que_as_referenciam(self):
        ordem = [s.tabela for s in SINCRONIAS]
        for fato in dimensional.FATOS:
            self.assertIn(fato, ordem)
            for dim in dimensional.DIMENSOES:
                self.assertLess(ordem.index(dim), ordem.index(fato))

    def test_fatos_viajam_sem_chave_substituta(self):
        """sk_curso, sk_campus e sk_perfil são identidades de cada banco: a exportação leva atributos naturais e o destino religa."""
        for s in SINCRONIAS:
            if s.tabela in dimensional.FATOS:
                self.assertNotRegex(s.exportar.split("FROM")[0], r"\bsk_(curso|campus|perfil)\b")
                self.assertIn("FROM tmp", s.inserir)


if __name__ == "__main__":
    unittest.main()

"""
Testes unitários da rotina de auditoria e reconciliação do Supabase (sem PostgreSQL).

Cobrem os caminhos em que a auditoria poderia falhar aberta: contagem que dá erro, tabela de
migrações ausente, reconciliação divergente ou sem banco local, papel público com acesso a silver
e célula abaixo de k = 5.

Uso:
    python3 -m unittest tests/test_unit_reconciliar_supabase.py
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db import reconciliar_supabase as rs  # noqa: E402


class ConexaoFalsa:
    """Responde a cada consulta pela primeira regra cujo trecho aparece no SQL.

    A resposta é uma tupla (fetchone), uma lista (fetchall), uma exceção (levantada) ou uma função
    dos parâmetros que devolve uma dessas."""

    def __init__(self, regras, ssl=True):
        self.regras = regras
        self.pgconn = SimpleNamespace(ssl_in_use=ssl)

    def execute(self, sql, params=None):
        for trecho, resposta in self.regras:
            if trecho in sql:
                if callable(resposta):
                    resposta = resposta(sql, params)
                if isinstance(resposta, Exception):
                    raise resposta
                return SimpleNamespace(fetchone=lambda r=resposta: r, fetchall=lambda r=resposta: r)
        raise AssertionError(f"Consulta inesperada: {sql}")


def contagens(por_tabela, padrao=0):
    """Regra de `SELECT count(*) FROM "esq"."tab"` a partir de um dicionário por tabela."""
    def responder(sql, _params):
        tabela = sql.split("FROM")[1].strip().replace('"', "")
        valor = por_tabela.get(tabela, padrao)
        return valor if isinstance(valor, Exception) else (valor,)
    return responder


def auditoria_aprovada(**substituir):
    auditoria = {
        "data_execucao": "2026-11-03T00:00:00Z",
        "extensao_vector": {"instalada": True, "versao": "0.8.2", "status": "OK"},
        "migracoes": {"status": "OK", "erro": None, "total_locais": 25, "total_aplicadas": 25,
                      "pendentes": [], "extras_no_destino": []},
        "controle_acesso": {"papel_existe": True, "papeis_conferidos": ["observatorio_leitura", "public"],
                            "exposicoes": [], "leitura_gold_busca": {"gold": True, "busca": True},
                            "isolamento_ok": True, "status": "OK"},
        "privacidade_lgpd": {"status": "OK", "linhas_vazadas": 0, "tabelas_inconclusivas": 0,
                             "tabelas_auditadas": {"silver.discentes": {"existe": True, "linhas": 0, "status": "OK"}}},
        "celula_minima": {"status": "OK", "minimo": 5, "tabelas": {
            "gold.fato_pibic_perfil": {"coluna": "total_projetos", "abaixo_do_minimo": 0, "status": "OK"}}},
        "reconciliacao": [{"tabela": "gold.retencao_cursos_unb", "qtd_remota": 95, "qtd_local": 95,
                           "status": "RECONCILIADO"}],
        "limites": {"tamanho_legivel": "138 MB", "tamanho_mb": 138.0, "cota_mb": 500.0, "pct_uso": 27.6,
                    "sessoes_no_banco": 5, "ssl": True, "status": "OK"},
    }
    auditoria.update(substituir)
    auditoria.setdefault("status_geral", rs.veredito(auditoria))
    return auditoria


class TestExtensaoEMigracoes(unittest.TestCase):
    def test_extensao_vector_instalada_e_ausente(self):
        self.assertEqual(rs.verificar_extensao_vector(ConexaoFalsa([("pg_extension", ("0.8.2",))]))["status"], "OK")
        self.assertEqual(rs.verificar_extensao_vector(ConexaoFalsa([("pg_extension", None)]))["status"], "FALHA")

    def test_migracoes_em_dia(self):
        locais = sorted(f.name for f in rs.MIGRATIONS_DIR.glob("*.sql"))
        res = rs.verificar_migracoes(ConexaoFalsa([("schema_migrations", [(m,) for m in locais])]))
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["total_aplicadas"], res["total_locais"])

    def test_migracao_pendente(self):
        locais = sorted(f.name for f in rs.MIGRATIONS_DIR.glob("*.sql"))
        res = rs.verificar_migracoes(ConexaoFalsa([("schema_migrations", [(m,) for m in locais[:-1]])]))
        self.assertEqual((res["status"], res["pendentes"]), ("PENDENTE", [locais[-1]]))

    def test_sem_tabela_de_migracoes_o_relatorio_sai_sem_keyerror(self):
        res = rs.verificar_migracoes(ConexaoFalsa([("schema_migrations", Exception("relation does not exist"))]))
        self.assertEqual(res["status"], "ERRO")
        self.assertEqual(res["total_aplicadas"], 0)
        auditoria = auditoria_aprovada(migracoes=res)
        self.assertEqual(rs.veredito(auditoria), "REQUER_ATENCAO")
        self.assertIn("relation does not exist", rs.formatar_relatorio_markdown(auditoria))
        self.assertIn("0/", rs.formatar_resumo(auditoria))


class TestPrivacidade(unittest.TestCase):
    TABELAS = ["bronze.sigra_discentes", "silver.discentes"]

    def conexao(self, por_tabela):
        return ConexaoFalsa([("to_regclass", (True,)), ("SELECT count(*) FROM", contagens(por_tabela))])

    def test_bronze_e_silver_vazias(self):
        res = rs.verificar_privacidade_lgpd(self.conexao({}), self.TABELAS)
        self.assertEqual((res["status"], res["linhas_vazadas"]), ("OK", 0))

    def test_linha_em_silver_e_falha_critica(self):
        res = rs.verificar_privacidade_lgpd(self.conexao({"silver.discentes": 100}), self.TABELAS)
        self.assertEqual((res["status"], res["linhas_vazadas"]), ("FALHA_CRITICA", 100))

    def test_contagem_que_falha_nao_vira_conforme(self):
        res = rs.verificar_privacidade_lgpd(self.conexao({"silver.discentes": Exception("permission denied")}),
                                            self.TABELAS)
        self.assertEqual(res["status"], "INCONCLUSIVO")
        self.assertIsNone(res["tabelas_auditadas"]["silver.discentes"]["linhas"])
        auditoria = auditoria_aprovada(privacidade_lgpd=res)
        self.assertEqual(rs.veredito(auditoria), "REQUER_ATENCAO")
        self.assertNotIn("✅ Nenhuma linha", rs.formatar_relatorio_markdown(auditoria))

    def test_tabela_nova_do_catalogo_entra_na_auditoria(self):
        conn = ConexaoFalsa([("pg_class", [("silver.tabela_nova",), ("silver.discentes",)])])
        tabelas = rs.tabelas_restritas(conn)
        self.assertIn("silver.tabela_nova", tabelas)
        self.assertTrue(set(rs.TABELAS_SENSIVEIS_MINIMAS) <= set(tabelas))


class TestCelulaMinima(unittest.TestCase):
    def test_gold_sem_celula_pequena(self):
        res = rs.verificar_celula_minima(ConexaoFalsa([("FILTER", (0,))]))
        self.assertEqual(res["status"], "OK")

    def test_celula_abaixo_de_cinco_e_falha_critica(self):
        def responder(sql, _params):
            return (2,) if "fato_pibic_perfil" in sql else (0,)
        res = rs.verificar_celula_minima(ConexaoFalsa([("FILTER", responder)]))
        self.assertEqual(res["status"], "FALHA_CRITICA")
        self.assertEqual(rs.veredito(auditoria_aprovada(celula_minima=res)), "FALHA_CRITICA")


class TestControleDeAcesso(unittest.TestCase):
    TABELAS = ["silver.discentes"]

    def conexao(self, papeis=("observatorio_leitura", "anon"), usage=(), select=()):
        return ConexaoFalsa([
            ("pg_roles", [(p,) for p in papeis]),
            ("to_regclass", (True,)),
            ("has_schema_privilege('observatorio_leitura'", (True,)),
            ("has_schema_privilege", lambda _s, p: ((p[0], p[1]) in usage,)),
            ("has_table_privilege", lambda _s, p: ((p[0], p[1]) in select,)),
        ])

    def test_nenhum_papel_alcanca_bronze_e_silver(self):
        res = rs.verificar_controle_acesso(self.conexao(), self.TABELAS)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["papeis_conferidos"], ["observatorio_leitura", "anon", "public"])

    def test_anon_com_usage_em_silver(self):
        res = rs.verificar_controle_acesso(self.conexao(usage={("anon", "silver")}), self.TABELAS)
        self.assertEqual(res["status"], "ALERTA")
        self.assertIn("anon: USAGE em silver", res["exposicoes"])

    def test_select_concedido_a_public_numa_tabela_sensivel(self):
        res = rs.verificar_controle_acesso(self.conexao(select={("public", "silver.discentes")}), self.TABELAS)
        self.assertIn("public: SELECT em silver.discentes", res["exposicoes"])

    def test_sem_papel_de_leitura(self):
        res = rs.verificar_controle_acesso(self.conexao(papeis=()), self.TABELAS)
        self.assertEqual(res["status"], "ALERTA")


class TestReconciliacao(unittest.TestCase):
    def setUp(self):
        sincronias = [SimpleNamespace(tabela="gold.retencao_cursos_unb")]
        self.patch = mock.patch.object(rs, "SINCRONIAS", sincronias)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def status(self, remoto, local):
        conn_local = None if local is None else ConexaoFalsa([("count", contagens({}, local))])
        relatorio = rs.reconciliar_contagens(ConexaoFalsa([("count", contagens({}, remoto))]), conn_local)
        return {r["tabela"]: r["status"] for r in relatorio}

    def test_mesmas_contagens(self):
        self.assertEqual(self.status(95, 95)["gold.retencao_cursos_unb"], "RECONCILIADO")

    def test_supabase_com_linhas_que_o_local_nao_tem_mais(self):
        self.assertEqual(self.status(97, 95)["gold.retencao_cursos_unb"], "RECONCILIADO_COM_EXTRAS")

    def test_supabase_com_menos_linhas(self):
        self.assertEqual(self.status(90, 95)["gold.retencao_cursos_unb"], "DIVERGENTE")

    def test_sem_banco_local_nao_reconcilia(self):
        self.assertEqual(self.status(95, None)["gold.retencao_cursos_unb"], "NAO_VERIFICADO")

    def test_erro_de_leitura(self):
        self.assertEqual(self.status(Exception("timeout"), 95)["gold.retencao_cursos_unb"], "ERRO")

    def test_a_view_do_painel_tambem_e_reconciliada(self):
        self.assertIn("gold.mv_dashboard_executivo", self.status(1, 1))


class TestVeredito(unittest.TestCase):
    def test_tudo_ok(self):
        self.assertEqual(rs.veredito(auditoria_aprovada()), "APROVADO")

    def test_reconciliacao_entra_no_veredito(self):
        for status in ("DIVERGENTE", "ERRO", "NAO_VERIFICADO"):
            with self.subTest(status=status):
                auditoria = auditoria_aprovada(reconciliacao=[{"tabela": "t", "qtd_remota": 1, "qtd_local": 2,
                                                               "status": status}])
                self.assertEqual(rs.veredito(auditoria), "REQUER_ATENCAO")

    def test_extras_no_supabase_nao_reprovam(self):
        auditoria = auditoria_aprovada(reconciliacao=[{"tabela": "t", "qtd_remota": 3, "qtd_local": 2,
                                                       "status": "RECONCILIADO_COM_EXTRAS"}])
        self.assertEqual(rs.veredito(auditoria), "APROVADO")

    def test_vazamento_e_falha_critica(self):
        auditoria = auditoria_aprovada(privacidade_lgpd={"status": "FALHA_CRITICA", "linhas_vazadas": 3,
                                                         "tabelas_inconclusivas": 0, "tabelas_auditadas": {}})
        self.assertEqual(rs.veredito(auditoria), "FALHA_CRITICA")

    def test_verificar_devolve_falso_quando_nao_aprova(self):
        reprovada = auditoria_aprovada(status_geral="REQUER_ATENCAO")
        with mock.patch.object(rs, "executar_auditoria_completa", return_value=reprovada), \
                mock.patch("builtins.print"):
            self.assertFalse(rs.verificar("postgresql://supabase", None))
        with mock.patch.object(rs, "executar_auditoria_completa",
                               return_value=auditoria_aprovada(status_geral="APROVADO")), \
                mock.patch("builtins.print"):
            self.assertTrue(rs.verificar("postgresql://supabase", None))

    def test_conexoes_sem_prepared_statement(self):
        """O pooler transacional do Supabase não mantém prepared statement entre transações."""
        conexoes = []

        def conectar(url, **kwargs):
            conexoes.append(kwargs)
            raise rs.psycopg.OperationalError("parar aqui")

        with mock.patch.object(rs.psycopg, "connect", side_effect=conectar), self.assertRaises(rs.psycopg.OperationalError):
            rs.executar_auditoria_completa("postgresql://supabase", "postgresql://local")
        self.assertIsNone(conexoes[0]["prepare_threshold"])

    def test_main_sai_com_erro_quando_nao_aprova(self):
        with mock.patch.object(rs, "ler_variavel", return_value="postgresql://supabase"), \
                mock.patch.object(rs, "verificar", return_value=False), \
                self.assertRaises(SystemExit) as saida:
            rs.main([])
        self.assertEqual(saida.exception.code, 1)


class TestLimites(unittest.TestCase):
    def conexao(self, ssl=True, mb=138):
        return ConexaoFalsa([
            ("pg_size_pretty", (f"{mb} MB",)),
            ("pg_database_size", (mb * 1024 * 1024,)),
            ("pg_stat_activity", (5,)),
        ], ssl=ssl)

    def test_percentual_da_cota(self):
        res = rs.verificar_limites_recursos(self.conexao())
        self.assertEqual(res["status"], "OK")
        self.assertAlmostEqual(res["pct_uso"], 27.6, places=1)

    def test_sem_ssl(self):
        self.assertEqual(rs.verificar_limites_recursos(self.conexao(ssl=False))["status"], "ALERTA")

    def test_perto_da_cota(self):
        self.assertEqual(rs.verificar_limites_recursos(self.conexao(mb=460))["status"], "ALERTA")


class TestRelatorio(unittest.TestCase):
    def test_relatorio_aprovado(self):
        md = rs.formatar_relatorio_markdown(auditoria_aprovada(status_geral="APROVADO"))
        for trecho in ("APROVADO", "pgvector", "gold.retencao_cursos_unb", "k ≥ 5", "Conexão por SSL"):
            self.assertIn(trecho, md)

    def test_exposicao_aparece_no_relatorio(self):
        acesso = dict(auditoria_aprovada()["controle_acesso"], exposicoes=["anon: USAGE em silver"],
                      isolamento_ok=False, status="ALERTA")
        md = rs.formatar_relatorio_markdown(auditoria_aprovada(status_geral="REQUER_ATENCAO", controle_acesso=acesso))
        self.assertIn("anon: USAGE em silver", md)


if __name__ == "__main__":
    unittest.main()

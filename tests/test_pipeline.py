"""
Suíte de Testes Automatizados - Pipeline de Retenção e Formatura UnB
Valida integridade de esquema, contratos de dados, taxa de casamento de joins
e conformidade com as regras metodológicas do Challenge.

As camadas são lidas do PostgreSQL (o pipeline grava cada uma direto no banco).
Sem banco acessível, os testes de dados são pulados.
"""

import sys
from pathlib import Path
import unittest
import pandas as pd
import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar
from src.db.tabelas import ler, ler_relatorio, tem_linhas
from src.pipeline.build_gold import normalize_turno_grupo, normalize_categoria_grau, build_area_por_curso


class TestCanonicalNormalization(unittest.TestCase):
    """Testes offline (sem dependência de dados brutos) das regras de normalização."""

    def test_turno_unifica_matutino_vespertino_em_diurno(self):
        self.assertEqual(normalize_turno_grupo("MATUTINO E VESPERTINO"), "DIURNO")
        self.assertEqual(normalize_turno_grupo("MATUTINO"), "DIURNO")
        self.assertEqual(normalize_turno_grupo("VESPERTINO"), "DIURNO")
        self.assertEqual(normalize_turno_grupo("DIURNO"), "DIURNO")

    def test_turno_preserva_noturno_e_integral(self):
        self.assertEqual(normalize_turno_grupo("NOTURNO"), "NOTURNO")
        self.assertEqual(normalize_turno_grupo("INTEGRAL"), "INTEGRAL")

    def test_categoria_grau_licenciatura(self):
        self.assertEqual(normalize_categoria_grau("LICENCIADO"), "LICENCIATURA")

    def test_categoria_grau_bacharelado_inclui_titulacoes_profissionais(self):
        for grau in ["BACHAREL", "ENGENHEIRO CIVIL", "MEDICO", "ARQUITETO E URBANISTA"]:
            self.assertEqual(normalize_categoria_grau(grau), "BACHARELADO")

    def test_build_area_por_curso_usa_entrada_propria_do_catalogo(self):
        df_cur = pd.DataFrame({
            "nome_curso_norm": ["FISICA", "QUIMICA"],
            "area_conhecimento_norm": ["CIENCIAS EXATAS E DA TERRA", "CIENCIAS EXATAS E DA TERRA"],
        })
        area_dict = build_area_por_curso(df_cur, ["FISICA"])
        self.assertEqual(area_dict["FISICA"], "CIENCIAS EXATAS E DA TERRA")

    def test_build_area_por_curso_herda_area_das_habilitacoes(self):
        df_cur = pd.DataFrame({
            "nome_curso_norm": ["COMUNICACAO SOCIAL - JORNALISMO", "COMUNICACAO SOCIAL - AUDIOVISUAL"],
            "area_conhecimento_norm": ["CIENCIAS SOCIAIS APLICADAS", "CIENCIAS SOCIAIS APLICADAS"],
        })
        area_dict = build_area_por_curso(df_cur, ["COMUNICACAO SOCIAL"])
        self.assertEqual(area_dict["COMUNICACAO SOCIAL"], "CIENCIAS SOCIAIS APLICADAS")

    def test_build_area_por_curso_nao_herda_quando_habilitacoes_divergem(self):
        df_cur = pd.DataFrame({
            "nome_curso_norm": ["CURSO X - A", "CURSO X - B"],
            "area_conhecimento_norm": ["CIENCIAS EXATAS E DA TERRA", "LINGUISTICA, LETRAS E ARTES"],
        })
        area_dict = build_area_por_curso(df_cur, ["CURSO X"])
        self.assertNotIn("CURSO X", area_dict)


class TestDataPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            conectar(connect_timeout=3).close()
        except psycopg.OperationalError as erro:
            raise unittest.SkipTest(f"Banco indisponível ({erro}). Suba com: docker compose up -d db")
        try:
            carregado = tem_linhas("gold.retencao_cursos_unb")
        except Exception:
            carregado = False
        if not carregado:
            raise unittest.SkipTest("Banco sem dados. Rode: bash scripts/rodar_pipeline.sh")

    def test_01_bronze_datasets_exist(self):
        """Verifica se os datasets brutos foram baixados corretamente via API."""
        required_tables = [
            "bronze.sigra_discentes",
            "bronze.estrutura_curricular",
            "bronze.cursos_graduacao",
        ]
        for tabela in required_tables:
            self.assertGreater(len(ler(tabela)), 100, f"Tabela Bronze vazia ou incompleta: {tabela}")

    def test_02_silver_transformation_integrity(self):
        """Verifica a limpeza, tipagem e decodificação na camada Silver."""
        for tabela in ("silver.sigra_graduacao", "silver.estrutura_curricular", "silver.cursos_graduacao"):
            self.assertTrue(tem_linhas(tabela), f"{tabela} vazia")

        df_sig = ler("silver.sigra_graduacao")
        self.assertIn("semestres_permanencia_valida", df_sig.columns)
        self.assertIn("tipo_saida_grupo", df_sig.columns)
        self.assertTrue((df_sig["nivel_norm"] == "GRADUACAO").all(), "Registros de pós-graduação presentes indevidamente")
        
        df_est = ler("silver.estrutura_curricular")
        self.assertIn("semestre_conclusao_ideal", df_est.columns)
        self.assertTrue(df_est["semestre_conclusao_ideal"].notna().any(), "Prazos ideais nulos na estrutura")

    def test_03_gold_layer_and_join_match_rate(self):
        """Verifica se a camada Gold atinge taxa de casamento superior a 90% e métricas consistentes."""
        join_meta = ler_relatorio("relatorio_casamento_joins")
        self.assertIsNotNone(join_meta, "relatório relatorio_casamento_joins ausente")

        taxa = join_meta.get("taxa_de_casamento_pct", 0)
        self.assertEqual(taxa, 100.0, f"Taxa de casamento abaixo de 100%: {taxa}%")

        self.assertTrue(tem_linhas("gold.regras_harmonizacao_canonicas"), "Regras de harmonização ausentes na Gold")

        df_gold = ler("gold.retencao_cursos_unb")
        self.assertGreater(len(df_gold), 50, "Quantidade de cursos na Gold muito reduzida")

        # Turno deve estar unificado (matutino/vespertino colapsados em Diurno)
        turnos_inesperados = set(df_gold["turno"].unique()) - {"DIURNO", "NOTURNO", "INTEGRAL"}
        self.assertFalse(turnos_inesperados, f"Valores de turno não normalizados encontrados: {turnos_inesperados}")

        # Curso genérico de ingresso comum (ex. Engenharia sem habilitação) permanece na tabela
        # Gold (compõe o panorama geral da UnB); é descartado só no dashboard, nas telas de
        # Visão Executiva e Detalhe por Curso (ver EXCLUDED_GENERIC_COURSES em build_gold.py).
        self.assertIn("ENGENHARIA", df_gold["curso"].values, "Curso genérico 'ENGENHARIA' deveria estar na tabela Gold")

        # Cursos com oferta dupla (Bacharelado e Licenciatura sob o mesmo nome, ex. Química)
        # aparecem como uma única linha marcada "MISTO", já que não há como atribuir cada
        # discente ao grau correto sem uma tabela oficial de opção -> grau (ver docs).
        quimica = df_gold[df_gold["curso"] == "QUIMICA"]
        self.assertEqual(len(quimica), 1, "QUIMICA deveria ser uma única linha unificada")
        self.assertEqual(quimica.iloc[0]["categoria_grau"], "MISTO")

        # Categoria de grau deve estar presente e limitada às classes de análise conhecidas
        # ("MISTO" cobre cursos com Bacharelado e Licenciatura sob o mesmo nome sem forma
        # confiável de separar os discentes por aluno - ver docs/dicionario_dados_gold.md).
        self.assertIn("categoria_grau", df_gold.columns)
        categorias_inesperadas = set(df_gold["categoria_grau"].unique()) - {"BACHARELADO", "LICENCIATURA", "MISTO"}
        self.assertFalse(categorias_inesperadas, f"Valores de categoria_grau inesperados: {categorias_inesperadas}")

        # Validar consistência matemática das métricas percentuais (0 <= pct <= 100)
        pct_cols = [
            "taxa_formatura_pct",
            "taxa_evasao_pct",
            "formados_tempo_ideal_pct",
            "formados_tempo_minimo_pct",
            "formados_acima_ideal_pct",
        ]
        for col in pct_cols:
            self.assertTrue((df_gold[col] >= 0).all(), f"Valor negativo encontrado na coluna {col}")
            self.assertTrue((df_gold[col] <= 100).all(), f"Valor superior a 100% encontrado na coluna {col}")
            
        # Validar semestres reais positivos
        valid_sem = df_gold["tempo_medio_real_semestres"].dropna()
        self.assertTrue((valid_sem >= 1).all(), "Tempo de formatura menor que 1 semestre encontrado")

    def test_04_privacy_safeguards(self):
        """Garante que a tabela Gold não expõe quase-identificadores sensíveis de discentes."""
        df_gold = ler("gold.retencao_cursos_unb")

        forbidden_cols = ["nome", "cpf", "data_nascimento", "sexo", "raca_cor", "cota_ingresso", "aluno"]
        for fcol in forbidden_cols:
            self.assertNotIn(fcol, df_gold.columns, f"Dado pessoal '{fcol}' exposto indevidamente na camada Gold")
            
        # Supressão de cursos com menos de 5 discentes
        self.assertTrue((df_gold["total_discentes_registrados"] >= 5).all(), "Grupo com k < 5 discentes não foi suprimido")

    def test_05_pibic_pipeline_and_social_metrics(self):
        """Verifica a integridade da ingestão, camada Silver e métricas sociais da Iniciação Científica (PIBIC)."""
        self.assertTrue(tem_linhas("bronze.bolsistas_iniciacao_cientifica"), "PIBIC ausente na Bronze")
        self.assertTrue(tem_linhas("silver.pibic_bolsistas"), "PIBIC ausente na Silver")
        self.assertTrue(tem_linhas("gold.pibic_social_unb"), "PIBIC ausente na Gold")
        pibic_meta = ler_relatorio("pibic_metricas_gerais")
        self.assertIsNotNone(pibic_meta, "relatório pibic_metricas_gerais ausente na Gold")

        # Validação Silver
        df_sil = ler("silver.pibic_bolsistas")
        self.assertIn("matricula_mascarada", df_sil.columns)
        self.assertIn("perfil_social_macro", df_sil.columns)
        self.assertIn("tipo_bolsa_norm", df_sil.columns)
        self.assertNotIn("discente", df_sil.columns, "Nome direto do discente mantido indevidamente")
        self.assertTrue(df_sil["matricula_mascarada"].str.contains(r"\*\*\*").all(), "Matrícula não foi devidamente mascarada")
        
        # Validação Gold
        df_gold_pibic = ler("gold.pibic_social_unb")
        self.assertTrue((df_gold_pibic["total_projetos"] >= 5).all(), "Supressão ética k < 5 falhou no PIBIC Gold")

        # Grande Área deve vir do catálogo oficial de cursos (CNPq/MEC), não do campo
        # autodeclarado "linha_pesquisa" da própria base de bolsistas — que classificava
        # cursos biológicos/de saúde (ex. Farmácia) incorretamente como "Artes e Humanidade".
        farmacia = df_gold_pibic[df_gold_pibic["curso_pibic_norm"] == "FARMACIA"]
        self.assertTrue((farmacia["area_conhecimento"] == "CIENCIAS DA SAUDE").all())

        # Cursos com grafias inconsistentes no campo de origem devem ser unificados em uma
        # única linha canônica (ex. Língua de Sinais Brasileira, antes duplicada no gráfico)
        sinais = df_gold_pibic[df_gold_pibic["curso_pibic_norm"].str.contains("SINAIS", na=False)]
        self.assertEqual(sinais["curso_pibic_norm"].nunique(), 1)

        # "Outra" não é uma Grande Área da taxonomia oficial CNPq/MEC — nenhum curso deve
        # cair nesse bucket residual (ver AREA_CONHECIMENTO_OVERRIDES/build_area_por_curso).
        self.assertNotIn("OUTRA", df_gold_pibic["area_conhecimento"].values)

        self.assertGreater(pibic_meta["total_projetos_ic"], 10000, "Volume de projetos de IC inconsistente")
        self.assertGreater(pibic_meta["investimento_publico_total_estimado"], 40000000.0, "Investimento total calculado inconsistente")
        self.assertGreater(pibic_meta["taxa_inclusao_cotistas_pct"], 30.0, "Taxa de cotistas menor que 30%")
        self.assertLess(pibic_meta["taxa_inclusao_cotistas_pct"], 50.0, "Taxa de cotistas maior que 50%")
        self.assertGreater(pibic_meta["taxa_trabalho_voluntario_pct"], 20.0, "Taxa de voluntários PIVIC inconsistente")

    def test_06_area_conhecimento_sem_bucket_residual_na_retencao(self):
        """A tabela de retenção também não deve ter cursos com Grande Área não classificada."""
        df_gold = ler("gold.retencao_cursos_unb")
        self.assertNotIn("OUTRA", df_gold["area_conhecimento"].values)


if __name__ == "__main__":
    unittest.main()


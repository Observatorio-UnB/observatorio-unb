"""
Suíte de Testes Automatizados - Pipeline de Retenção e Formatura UnB
Valida integridade de esquema, contratos de dados, taxa de casamento de joins
e conformidade com as regras metodológicas do Challenge.
"""

import json
import sys
from pathlib import Path
import unittest
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
BRONZE_DIR = BASE_DIR / "data" / "bronze"
SILVER_DIR = BASE_DIR / "data" / "silver"
GOLD_DIR = BASE_DIR / "data" / "gold"

sys.path.insert(0, str(BASE_DIR))
from src.pipeline.build_gold import normalize_turno_grupo, normalize_categoria_grau, build_area_por_curso, ofertas_por_curso
from src.pipeline.transform_silver import (categorize_forma_saida, semestre_pela_data_do_diploma, normalize_curso,
                                          valor_bolsa_no_periodo)
from src.ingestion.ckan_client import DATASETS_CONFIG, escolher_recurso


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
        self.assertEqual(normalize_categoria_grau("LICENCIATURA"), "LICENCIATURA")

    def test_evasao_inclui_mudanca_de_curso(self):
        """Mesma definição de evasão nas duas bases: o SIGAA não distingue o motivo do cancelamento."""
        self.assertEqual(categorize_forma_saida("Formatura"), "FORMATURA")
        for forma in ["Desligamento - Abandono", "Novo Vestibular", "Mudança de Curso", "Vestibular p/outra Habilitação"]:
            self.assertEqual(categorize_forma_saida(forma), "EVASAO", forma)
        self.assertEqual(categorize_forma_saida("Anulação de Registro"), "OUTROS")

    def test_semestre_pela_data_do_diploma(self):
        datas = pd.Series(["15/02/2023", "20/07/2023", "10/12/2023", None])
        saida = semestre_pela_data_do_diploma(datas)
        self.assertEqual(saida["ano_saida"].tolist()[:3], [2022, 2023, 2023])
        self.assertEqual(saida["semestre_saida"].tolist()[:3], [2, 1, 2])
        self.assertTrue(saida.iloc[3].isna().all())

    def test_ingestao_escolhe_o_recurso_mais_recente(self):
        """Baixa a versão mais recente que casa com o padrão; arquivos com nome e CPF ficam de fora."""
        def arquivo(chave):
            meta = json.loads((BRONZE_DIR / f"metadata_{DATASETS_CONFIG[chave]['package_id']}.json").read_text())
            return escolher_recurso(meta["resources"], DATASETS_CONFIG[chave]["resource_pattern"])["url"].rsplit("/", 1)[-1]
        self.assertEqual(arquivo("cursos_graduacao"), "cursos-de-graduao-08-2024.csv")
        recursos = [{"url": "a/sigaa.csv", "last_modified": "2024-07-15"},
                    {"url": "a/sigaa_2025_2.csv", "last_modified": "2026-01-10"}]
        self.assertEqual(escolher_recurso(recursos, DATASETS_CONFIG["sigaa"]["resource_pattern"])["url"], "a/sigaa_2025_2.csv")
        self.assertEqual(arquivo("sigaa"), "sigaa.csv")
        self.assertIsNone(escolher_recurso([{"url": "x/sigaa_concluintes_2025_1.csv"}], DATASETS_CONFIG["sigaa"]["resource_pattern"]))
        self.assertIsNone(escolher_recurso([{"url": "x/sigaa_concluintes_2025_1.csv"}], DATASETS_CONFIG["sigaa_ativos"]["resource_pattern"]))
        self.assertEqual(arquivo("sigaa_ativos"), "sigaa_ativos_2025_1.csv")

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

    def test_normalize_curso_remove_prefixo_guarda_chuva(self):
        self.assertEqual(normalize_curso("COMUNICAÇÃO SOCIAL - JORNALISMO"), "JORNALISMO")
        self.assertEqual(normalize_curso("Ciências Sociais - Antropologia"), "ANTROPOLOGIA")
        self.assertEqual(normalize_curso("CIÊNCIAS SOCIAIS"), "CIENCIAS SOCIAIS")
        self.assertEqual(normalize_curso("LETRAS - TRADUÇÃO - INGLÊS"), "LETRAS - TRADUCAO - INGLES")

    def test_valor_bolsa_soma_os_meses_de_cada_valor(self):
        vig = pd.DataFrame({"vigente_desde": ["2012-07", "2023-02"], "valor_mensal": [400.0, 700.0]})
        # Ciclo 2022: jul/2022 a jun/2023 = 7 meses a 400 + 5 a 700
        self.assertEqual(valor_bolsa_no_periodo(pd.Timestamp("2022-07-24"), pd.Timestamp("2023-06-24"), vig), 7 * 400 + 5 * 700)
        self.assertEqual(valor_bolsa_no_periodo(pd.Timestamp("2018-08-01"), pd.Timestamp("2019-07-26"), vig), 12 * 400)
        # Antes da primeira vigência vale o primeiro valor
        self.assertEqual(valor_bolsa_no_periodo(pd.Timestamp("2012-01-10"), pd.Timestamp("2012-12-10"), vig), 12 * 400)

    def test_ofertas_por_curso_nao_escolhe_oferta_arbitraria(self):
        df_cur = pd.DataFrame({
            "nome_curso_norm": ["DIREITO", "DIREITO", "ENFERMAGEM", "ENFERMAGEM"],
            "turno_norm": ["DIURNO", "NOTURNO", "DIURNO", "MATUTINO"],
            "campus_norm": ["DARCY RIBEIRO", "DARCY RIBEIRO", "DARCY RIBEIRO", "CEILANDIA"],
        })
        ofertas = ofertas_por_curso(df_cur)
        self.assertEqual(ofertas["DIREITO"], ("DIURNO E NOTURNO", "DARCY RIBEIRO"))
        self.assertEqual(ofertas["ENFERMAGEM"], ("DIURNO", "MULTICAMPUS"))


class TestDataPipeline(unittest.TestCase):
    
    def test_01_bronze_datasets_exist(self):
        """Verifica se os datasets brutos foram baixados corretamente via API."""
        required_files = [
            "sigra_discentes.csv",
            "sigaa_discentes.csv",
            "sigaa_ativos.csv",
            "estrutura_curricular.csv",
            "cursos_graduacao.csv",
        ]
        for fname in required_files:
            fpath = BRONZE_DIR / fname
            self.assertTrue(fpath.exists(), f"Arquivo Bronze ausente: {fname}")
            self.assertGreater(fpath.stat().st_size, 1000, f"Arquivo Bronze vazio ou corrompido: {fname}")

    def test_02_silver_transformation_integrity(self):
        """Verifica a limpeza, tipagem e decodificação na camada Silver."""
        sig_path = SILVER_DIR / "discentes_graduacao_silver.csv"
        est_path = SILVER_DIR / "estrutura_curricular_silver.csv"
        cur_path = SILVER_DIR / "cursos_graduacao_silver.csv"
        
        self.assertTrue(sig_path.exists(), "discentes_graduacao_silver.csv ausente")
        self.assertTrue(est_path.exists(), "estrutura_curricular_silver.csv ausente")
        self.assertTrue(cur_path.exists(), "cursos_graduacao_silver.csv ausente")
        
        df_sig = pd.read_csv(sig_path, low_memory=False)
        self.assertEqual(set(df_sig["fonte"]), {"SIGRA", "SIGAA"})
        # O SIGRA só tem vínculos encerrados; ativos vêm apenas do SIGAA.
        self.assertFalse(((df_sig["fonte"] == "SIGRA") & (df_sig["tipo_saida_grupo"] == "ATIVO")).any())
        self.assertIn("semestres_permanencia_valida", df_sig.columns)
        self.assertIn("tipo_saida_grupo", df_sig.columns)
        self.assertTrue((df_sig["nivel_norm"] == "GRADUACAO").all(), "Registros de pós-graduação presentes indevidamente")
        
        # Catálogo junta todas as versões: código que saiu da lista (414162, cadastro duplicado de Jornalismo em 2022) continua,
        # marcado como fora do vigente; curso novo (Ed. Física ciclo básico, 2024) entra.
        df_cur = pd.read_csv(cur_path)
        self.assertTrue(df_cur["id_curso"].is_unique)
        self.assertFalse(df_cur.loc[df_cur["id_curso"] == 414162, "no_catalogo_vigente"].item())
        self.assertTrue(df_cur["nome_curso_norm"].str.startswith("EDUCACAO FISICA - CICLO BASICO").any())

        df_est = pd.read_csv(est_path)
        self.assertIn("semestre_conclusao_ideal", df_est.columns)
        self.assertTrue(df_est["semestre_conclusao_ideal"].notna().any(), "Prazos ideais nulos na estrutura")

    def test_03_gold_layer_and_join_match_rate(self):
        """Verifica se a camada Gold atinge taxa de casamento superior a 90% e métricas consistentes."""
        gold_path = GOLD_DIR / "retencao_cursos_unb.csv"
        join_meta_path = GOLD_DIR / "relatorio_casamento_joins.json"
        
        self.assertTrue(gold_path.exists(), "retencao_cursos_unb.csv ausente")
        self.assertTrue(join_meta_path.exists(), "relatorio_casamento_joins.json ausente")
        
        with open(join_meta_path, "r", encoding="utf-8") as f:
            join_meta = json.load(f)
            
        taxa = join_meta.get("taxa_de_casamento_pct", 0)
        self.assertEqual(taxa, 100.0, f"Taxa de casamento abaixo de 100%: {taxa}%")
        
        regras_path = GOLD_DIR / "regras_harmonizacao_canonicas.json"
        self.assertTrue(regras_path.exists(), "regras_harmonizacao_canonicas.json ausente na Gold")
        
        df_gold = pd.read_csv(gold_path)
        self.assertGreater(len(df_gold), 50, "Quantidade de cursos na Gold muito reduzida")

        # Turno deve estar unificado (matutino/vespertino colapsados em Diurno)
        turnos_inesperados = set(df_gold["turno"].unique()) - {"DIURNO", "NOTURNO", "INTEGRAL", "DIURNO E NOTURNO"}
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
        gold_path = GOLD_DIR / "retencao_cursos_unb.csv"
        df_gold = pd.read_csv(gold_path)
        
        forbidden_cols = ["nome", "cpf", "data_nascimento", "sexo", "raca_cor", "cota_ingresso", "aluno"]
        for fcol in forbidden_cols:
            self.assertNotIn(fcol, df_gold.columns, f"Dado pessoal '{fcol}' exposto indevidamente na camada Gold")
            
        # Supressão de cursos com menos de 5 discentes
        self.assertTrue((df_gold["total_discentes_registrados"] >= 5).all(), "Grupo com k < 5 discentes não foi suprimido")

    def test_04b_ativos_hoje(self):
        """Ativos hoje: k >= 5, sem dado pessoal e contagens coerentes entre si."""
        df = pd.read_csv(GOLD_DIR / "ativos_hoje_cursos_unb.csv")
        self.assertFalse({"aluno", "data_nascimento", "sexo", "raca_cor"} & set(df.columns))
        self.assertTrue((df["total_ativos_hoje"] >= 5).all())
        self.assertTrue((df["ativos_acima_prazo_maximo"] <= df["ativos_acima_prazo_ideal"]).all())
        self.assertTrue((df["ativos_acima_prazo_ideal"] <= df["total_ativos_hoje"]).all())
        self.assertEqual(df["periodo_referencia"].nunique(), 1)

    def test_04c_ativos_sem_dado_identificador(self):
        """A lista de ativos do portal tem nome e CPF; a Bronze só pode ter as colunas minimizadas."""
        colunas = pd.read_csv(BRONZE_DIR / "sigaa_ativos.csv", nrows=0).columns
        self.assertEqual(list(colunas), DATASETS_CONFIG["sigaa_ativos"]["colunas"])

    def test_05_pibic_pipeline_and_social_metrics(self):
        """Verifica a integridade da ingestão, camada Silver e métricas sociais da Iniciação Científica (PIBIC)."""
        bronze_pibic = BRONZE_DIR / "bolsistas_iniciacao_cientifica.csv"
        silver_pibic = SILVER_DIR / "pibic_bolsistas_silver.csv"
        gold_pibic = GOLD_DIR / "pibic_social_unb.csv"
        json_pibic = GOLD_DIR / "pibic_metricas_gerais.json"
        
        self.assertTrue(bronze_pibic.exists(), "bolsistas_iniciacao_cientifica.csv ausente na Bronze")
        self.assertTrue(silver_pibic.exists(), "pibic_bolsistas_silver.csv ausente na Silver")
        self.assertTrue(gold_pibic.exists(), "pibic_social_unb.csv ausente na Gold")
        self.assertTrue(json_pibic.exists(), "pibic_metricas_gerais.json ausente na Gold")
        
        # Validação Silver
        df_sil = pd.read_csv(silver_pibic)
        self.assertIn("perfil_social_macro", df_sil.columns)
        self.assertIn("tipo_bolsa_norm", df_sil.columns)
        # Minimização na ingestão: nome, matrícula e orientador nem chegam à Bronze.
        colunas_bronze = pd.read_csv(bronze_pibic, nrows=0).columns.tolist()
        self.assertEqual(colunas_bronze, DATASETS_CONFIG["pibic"]["colunas"])
        for pessoal in ("discente", "matricula", "orientador", "matricula_mascarada", "orientador_norm"):
            self.assertNotIn(pessoal, df_sil.columns)
        
        # Validação Gold
        df_gold_pibic = pd.read_csv(gold_pibic)
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

        with open(json_pibic, "r", encoding="utf-8") as f:
            pibic_meta = json.load(f)

        self.assertGreater(pibic_meta["total_projetos_ic"], 10000, "Volume de projetos de IC inconsistente")
        self.assertGreater(pibic_meta["investimento_publico_total_estimado"], 40000000.0, "Investimento total calculado inconsistente")
        self.assertGreater(pibic_meta["taxa_inclusao_cotistas_pct"], 30.0, "Taxa de cotistas menor que 30%")
        self.assertLess(pibic_meta["taxa_inclusao_cotistas_pct"], 50.0, "Taxa de cotistas maior que 50%")
        self.assertGreater(pibic_meta["taxa_trabalho_voluntario_pct"], 20.0, "Taxa de voluntários PIVIC inconsistente")

    def test_06_area_conhecimento_sem_bucket_residual_na_retencao(self):
        """A tabela de retenção também não deve ter cursos com Grande Área não classificada."""
        gold_path = GOLD_DIR / "retencao_cursos_unb.csv"
        df_gold = pd.read_csv(gold_path)
        self.assertNotIn("OUTRA", df_gold["area_conhecimento"].values)


if __name__ == "__main__":
    unittest.main()


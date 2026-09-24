"""
Pipeline de Transformação - Camada Bronze -> Camada Silver
Realiza limpeza, decodificação de encodings, remoção de padding,
padronização semântica, cálculo de permanência e tipagem de dados.
"""

import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("transform_silver")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BRONZE_DIR = BASE_DIR / "data" / "bronze"
SILVER_DIR = BASE_DIR / "data" / "silver"


def normalize_text(text: Optional[str]) -> str:
    """Normaliza texto: remove acentos, espaços extras e converte para maiúsculas."""
    if text is None or pd.isna(text):
        return ""
    text = str(text).strip()
    if text.upper() in ["NULL", "NONE", "NAN", "-", ""]:
        return ""
    # Normalização NFKD para decompor caracteres acentuados
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_text).upper()


def categorize_forma_saida(forma: str) -> str:
    """Classifica a forma de saída em categorias padronizadas de análise."""
    forma_norm = normalize_text(forma)
    if "FORMATURA" in forma_norm:
        return "FORMATURA"
    elif any(k in forma_norm for k in ["ABANDONO", "NAO CUMPRIU CONDICAO", "JUBILAMENTO", "REPR 3 VEZES", "DESLIGAMENTO"]):
        return "EVASAO_DESLIGAMENTO"
    elif any(k in forma_norm for k in ["NOVO VESTIBULAR", "TRANSFERENCIA", "MUDANCA DE CURSO", "DUPLA HABILITACAO"]):
        return "MUDANCA_INTERNA"
    else:
        return "OUTROS"


def process_sigra() -> pd.DataFrame:
    """Processa a base bruta do SIGRA e gera a versão Silver de discentes de graduação."""
    raw_path = BRONZE_DIR / "sigra_discentes.csv"
    logger.info(f"Processando {raw_path.name}...")
    
    df = pd.read_csv(raw_path, sep=";", encoding="utf-8", on_bad_lines="skip", dtype=str)
    
    # 1. Filtrar apenas discentes de graduação
    df["nivel_norm"] = df["nivel"].apply(normalize_text)
    df_grad = df[df["nivel_norm"] == "GRADUACAO"].copy()
    
    # 2. Limpeza de campos textuais
    df_grad["curso_raw"] = df_grad["curso"].astype(str).str.strip()
    df_grad["curso_norm"] = df_grad["curso"].apply(normalize_text)
    df_grad["departamento_norm"] = df_grad["departamento"].apply(normalize_text)
    df_grad["forma_saida_norm"] = df_grad["forma_saida"].apply(normalize_text)
    df_grad["tipo_saida_grupo"] = df_grad["forma_saida"].apply(categorize_forma_saida)
    
    # 3. Tratamento de datas e períodos
    df_grad["ano_ingresso"] = pd.to_numeric(df_grad["ano_ingresso"], errors="coerce")
    
    # Parse do periodo_saida (ex: '20141' -> ano 2014, semestre 1)
    def parse_periodo_saida(val):
        val_str = str(val).strip().replace(".0", "")
        if len(val_str) == 5 and val_str.isdigit():
            ano = int(val_str[:4])
            sem = int(val_str[4])
            return ano, sem
        elif len(val_str) == 4 and val_str.isdigit():
            # Apenas o ano
            return int(val_str), 1
        return np.nan, np.nan

    parsed_periodo = df_grad["periodo_saida"].apply(parse_periodo_saida)
    df_grad["ano_saida"] = [p[0] for p in parsed_periodo]
    df_grad["semestre_saida"] = [p[1] for p in parsed_periodo]
    
    # 4. Cálculo do tempo de permanência em semestres
    # Fórmula: 2 * (ano_saida - ano_ingresso) + semestre_saida
    # Documentação de incerteza: assume ingresso no semestre 1 como baseline
    df_grad["semestres_permanencia"] = (
        2 * (df_grad["ano_saida"] - df_grad["ano_ingresso"]) + df_grad["semestre_saida"]
    )
    
    # Filtro de sanidade (permanência entre 1 e 30 semestres)
    df_grad["semestres_permanencia_valida"] = df_grad["semestres_permanencia"].apply(
        lambda x: x if (pd.notna(x) and 1 <= x <= 30) else np.nan
    )
    
    out_path = SILVER_DIR / "sigra_graduacao_silver.csv"
    df_grad.to_csv(out_path, index=False, encoding="utf-8")
    logger.info(f"Salvo {out_path.name} com {len(df_grad):,} registros de graduação.")
    return df_grad


def process_estrutura_curricular() -> pd.DataFrame:
    """Processa a base bruta de estrutura curricular (resolvendo encoding latin-1)."""
    raw_path = BRONZE_DIR / "estrutura_curricular.csv"
    logger.info(f"Processando {raw_path.name}...")
    
    df = pd.read_csv(raw_path, sep=";", encoding="latin-1", on_bad_lines="skip", dtype=str)
    
    # Normalização de nomes de cursos
    df["nome_curso_norm"] = df["nome_curso"].apply(normalize_text)
    df["nome_matriz_norm"] = df["nome_matriz"].apply(normalize_text)
    
    # Conversão de colunas numéricas de semestres e horas
    num_cols = [
        "semestre_conclusao_minimo",
        "semestre_conclusao_ideal",
        "semestre_conclusao_maximo",
        "ch_total_minima",
        "cr_total_minimo",
        "ano_entrada_vigor",
    ]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        
    # Agregação por curso canônico para obter os prazos de referência consolidados
    # (seleciona o currículo com maior ch_total_minima ou mais recente)
    df_clean = df[df["nome_curso_norm"] != ""].copy()
    
    # Agrupamento para consolidar matriz de referência
    agg_dict = {
        "semestre_conclusao_minimo": "median",
        "semestre_conclusao_ideal": "median",
        "semestre_conclusao_maximo": "median",
        "ch_total_minima": "max",
        "cr_total_minimo": "max",
        "id_curso": "first",
    }
    df_consolidado = df_clean.groupby("nome_curso_norm", as_index=False).agg(agg_dict)
    
    out_path = SILVER_DIR / "estrutura_curricular_silver.csv"
    df_consolidado.to_csv(out_path, index=False, encoding="utf-8")
    logger.info(f"Salvo {out_path.name} com {len(df_consolidado):,} estruturas curriculares consolidadas.")
    return df_consolidado


def process_cursos_graduacao() -> pd.DataFrame:
    """Processa a base de cursos de graduação (resolvendo 'NULL' literais e metadados)."""
    raw_path = BRONZE_DIR / "cursos_graduacao.csv"
    logger.info(f"Processando {raw_path.name}...")
    
    df = pd.read_csv(raw_path, sep=",", encoding="utf-8", on_bad_lines="skip", dtype=str)
    
    df["nome_curso_norm"] = df["nome"].apply(normalize_text)
    df["turno_norm"] = df["turno"].apply(normalize_text)
    df["campus_norm"] = df["campus"].apply(normalize_text)
    df["grau_academico_norm"] = df["grau_academico"].apply(normalize_text)
    df["area_conhecimento_norm"] = df["area_conhecimento"].apply(normalize_text)
    df["unidade_responsavel_norm"] = df["unidade_responsavel"].apply(normalize_text)

    # O catálogo bruto da UnB classifica 13 cursos como "Outra", que não existe na
    # taxonomia oficial CNPq/MEC de Grande Área. Mapeamos manualmente para a área correta
    # de cada um (conferida contra a classificação oficial CNPq/MEC, não a de um curso
    # "irmão" na base bruta, já que esta também tem inconsistências — ex.: Ciências
    # Sociais aparece ora como "Ciências Sociais Aplicadas", ora como "Ciências Humanas").
    AREA_CONHECIMENTO_OVERRIDES = {
        "ARQUITETURA E URBANISMO": "CIENCIAS SOCIAIS APLICADAS",
        "CIENCIAS NATURAIS": "CIENCIAS HUMANAS",
        "CIENCIAS SOCIAIS": "CIENCIAS HUMANAS",
        "EDUCACAO DO CAMPO - MATEMATICA": "CIENCIAS HUMANAS",
        "EDUCACAO FISICA": "CIENCIAS DA SAUDE",
        "ENGENHARIA": "ENGENHARIAS",
        "ENGENHARIA AUTOMOTIVA": "ENGENHARIAS",
        "LETRAS - LINGUA INGLESA E RESPECTIVA LITERATURA": "LINGUISTICA, LETRAS E ARTES",
        "MUSEOLOGIA": "CIENCIAS SOCIAIS APLICADAS",
        "MUSICA": "LINGUISTICA, LETRAS E ARTES",
        "TEATRO": "LINGUISTICA, LETRAS E ARTES",
    }
    mask_outra = df["area_conhecimento_norm"] == "OUTRA"
    df.loc[mask_outra, "area_conhecimento_norm"] = (
        df.loc[mask_outra, "nome_curso_norm"].map(AREA_CONHECIMENTO_OVERRIDES).fillna("OUTRA")
    )
    ainda_outra = df.loc[df["area_conhecimento_norm"] == "OUTRA", "nome_curso_norm"].unique()
    if len(ainda_outra):
        logger.warning(
            f"Cursos sem Grande Área mapeada, adicione a AREA_CONHECIMENTO_OVERRIDES: {list(ainda_outra)}"
        )

    # Substituir literais NULL por NaN
    df = df.replace(["NULL", "NONE", "NAN", ""], np.nan)
    
    out_path = SILVER_DIR / "cursos_graduacao_silver.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")
    logger.info(f"Salvo {out_path.name} com {len(df):,} cursos cadastrados.")
    return df


# Código da UnB no cadastro de IES do INEP (Censo da Educação Superior).
CO_IES_UNB = 2


def process_inep_censo() -> pd.DataFrame:
    """
    Processa o recorte de cursos presenciais de universidades federais do Censo da Educação
    Superior (INEP), calculando as taxas por curso que permitem comparar a UnB com as demais
    federais (ver docs/fonte_inep_censo_superior.md).
    """
    raw_path = BRONZE_DIR / "inep_censo_superior_federais.csv"
    if not raw_path.exists():
        logger.warning(f"Arquivo {raw_path.name} não encontrado na camada Bronze. Pulando Censo INEP.")
        return pd.DataFrame()

    logger.info(f"Processando {raw_path.name} (Censo da Educação Superior - INEP)...")
    df = pd.read_csv(raw_path)

    df["curso_inep_norm"] = df["NO_CURSO"].apply(normalize_text)
    df["is_unb"] = df["CO_IES"] == CO_IES_UNB

    # Taxas do próprio Censo: a situação da matrícula é apurada no ano-censo, e não pelo
    # acompanhamento da coorte de ingresso - por isso estas taxas não são comparáveis com a
    # taxa de evasão da tabela de retenção (construída sobre o histórico do SIGRA).
    matriculas = df["QT_MAT"].replace(0, np.nan)
    df["taxa_trancamento_pct"] = (df["QT_SIT_TRANCADA"] / matriculas * 100).round(2)
    df["taxa_desvinculacao_pct"] = (df["QT_SIT_DESVINCULADO"] / matriculas * 100).round(2)

    vagas = df["QT_VG_TOTAL"].replace(0, np.nan)
    df["concorrencia_vestibular"] = (df["QT_INSCRITO_TOTAL"] / vagas).round(2)

    cols_silver = [
        "NU_ANO_CENSO",
        "CO_IES",
        "NO_IES",
        "is_unb",
        "CO_CURSO",
        "NO_CURSO",
        "curso_inep_norm",
        "QT_VG_TOTAL",
        "QT_INSCRITO_TOTAL",
        "QT_ING",
        "QT_MAT",
        "QT_CONC",
        "QT_SIT_TRANCADA",
        "QT_SIT_DESVINCULADO",
        "taxa_trancamento_pct",
        "taxa_desvinculacao_pct",
        "concorrencia_vestibular",
    ]
    df_silver = df[cols_silver].copy()

    out_path = SILVER_DIR / "inep_censo_superior_silver.csv"
    df_silver.to_csv(out_path, index=False, encoding="utf-8")
    logger.info(
        f"Salvo {out_path.name} com {len(df_silver):,} cursos de federais "
        f"({int(df_silver['is_unb'].sum())} da UnB)."
    )
    return df_silver


def process_pibic() -> pd.DataFrame:
    """
    Processa a base bruta de bolsistas de iniciação científica (PIBIC/PIVIC),
    aplicando sanitização LGPD, categorização social e mapeamento territorial.
    """
    raw_path = BRONZE_DIR / "bolsistas_iniciacao_cientifica.csv"
    if not raw_path.exists():
        logger.warning(f"Arquivo {raw_path.name} não encontrado na camada Bronze. Pulando PIBIC.")
        return pd.DataFrame()
        
    logger.info(f"Processando {raw_path.name} (Iniciação Científica & Análise Social)...")
    df = pd.read_csv(raw_path, sep=",", encoding="latin-1", on_bad_lines="skip", dtype=str)
    
    # 1. Normalização de textos
    df["titulo_norm"] = df["titulo"].apply(normalize_text)
    df["orientador_norm"] = df["orientador"].apply(normalize_text)
    df["linha_pesquisa_norm"] = df["linha_pesquisa"].apply(normalize_text)
    df["unidade_raw"] = df["unidade"].astype(str).str.strip()
    df["unidade_norm"] = df["unidade"].apply(normalize_text)
    df["status_norm"] = df["status"].apply(normalize_text)
    
    # 2. Parse temporal
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    
    # 3. Tipo de bolsa (Remunerada vs Voluntária PIVIC)
    def clean_tipo_bolsa(val):
        v = normalize_text(val)
        if "REMUNERADA" in v:
            return "REMUNERADA"
        elif "VOLUNTARIA" in v:
            return "VOLUNTARIA"
        return "NAO INFORMADO"
    df["tipo_bolsa_norm"] = df["tipo_de_bolsa"].apply(clean_tipo_bolsa)
    
    # 4. Categorização Social de Ingresso e Cotas
    def categorize_cota_pibic(val):
        v = normalize_text(val)
        if not v or v in ["NAO", "UNIVERSAL"]:
            return "AMPLA CONCORRENCIA", "AMPLA CONCORRENCIA", "NAO APLICAVEL", False
            
        is_ppi = any(k in v for k in ["PPI", "NEGRO", "INDIGENA"])
        is_pcd = "PCD" in v
        is_baixa_renda = "BAIXA RENDA" in v
        is_alta_renda = "ALTA RENDA" in v
        
        # Grupo detalhado
        if is_ppi and ("ESCOLA PUB" in v or "ESCOLA PUBLICA" in v):
            grupo = "ESCOLA PUBLICA - PPI"
        elif "ESCOLA PUB" in v or "ESCOLA PUBLICA" in v:
            grupo = "ESCOLA PUBLICA - NAO PPI"
        elif any(k in v for k in ["NEGRO", "INDIGENA"]):
            grupo = "COTAS RACIAIS (NEGRO/INDIGENA)"
        elif is_pcd:
            grupo = "COTAS PCD"
        else:
            grupo = "OUTRAS ACOES AFIRMATIVAS"
            
        # Renda
        if is_baixa_renda:
            faixa_renda = "BAIXA RENDA (<= 1.5 SM)"
        elif is_alta_renda:
            faixa_renda = "INDEPENDENTE DE RENDA"
        else:
            faixa_renda = "NAO ESPECIFICADO"
            
        perfil_macro = "PPI / ETNICO-RACIAL" if is_ppi else ("ESCOLA PUBLICA" if "ESCOLA PUB" in v else "OUTRAS COTAS")
        return perfil_macro, grupo, faixa_renda, True

    cota_results = df["cota"].apply(categorize_cota_pibic)
    df["perfil_social_macro"] = [r[0] for r in cota_results]
    df["cota_detalhe"] = [r[1] for r in cota_results]
    df["faixa_renda"] = [r[2] for r in cota_results]
    df["is_cotista"] = [r[3] for r in cota_results]
    
    # 5. Mapeamento Territorial de Campi
    def parse_campus_pibic(u_norm):
        if "GAMA" in u_norm:
            return "FGA - GAMA"
        elif "CEILANDIA" in u_norm:
            return "FCE - CEILANDIA"
        elif "PLANALTINA" in u_norm:
            return "FUP - PLANALTINA"
        return "DARCY RIBEIRO"
    df["campus"] = df["unidade_norm"].apply(parse_campus_pibic)
    
    # 6. Extração de Curso e Departamento
    # Prefixos genéricos usados de forma inconsistente no campo "unidade" do PIBIC
    # (ex.: "BACHARELADO EM FISICA" vs. "FISICA" no restante da base) e que impedem o
    # casamento com o nome canônico do curso se não forem removidos.
    CURSO_PREFIXOS_GENERICOS = re.compile(
        r"^(BACHARELADO EM |LICENCIATURA EM |GRADUACAO EM |GRADUACAO DE |CURSO DE |CURSO )",
        flags=re.IGNORECASE,
    )

    def parse_curso_pibic(u_raw):
        if pd.isna(u_raw) or "/" not in str(u_raw):
            return ""
        part = str(u_raw).split("/", 1)[1]
        # Remove sufixo de situação do discente ("- ALUNO: ATIVO", "- ALUNO: TRANCADO" etc.)
        # e o marcador final "- FORMANDO", em qualquer combinação.
        part = re.sub(r"-?\s*ALUNO:\s*\S+", "", part, flags=re.IGNORECASE)
        part = re.sub(r"-\s*FORMANDO\s*$", "", part, flags=re.IGNORECASE).strip()
        part = CURSO_PREFIXOS_GENERICOS.sub("", part.strip())
        return normalize_text(part)
        
    def parse_depto_pibic(u_raw):
        if pd.isna(u_raw) or "/" not in str(u_raw):
            return normalize_text(u_raw)
        return normalize_text(str(u_raw).split("/", 1)[0])
        
    df["curso_pibic_norm"] = df["unidade_raw"].apply(parse_curso_pibic)
    df["departamento_pibic_norm"] = df["unidade_raw"].apply(parse_depto_pibic)
    
    # 7. Cálculo de Investimento Público por Bolsa
    def calc_valor_bolsa(row):
        if row["tipo_bolsa_norm"] != "REMUNERADA":
            return 0.0
        ano = row["ano"]
        if pd.notna(ano) and ano >= 2023:
            return 700.0 * 12
        return 400.0 * 12
    df["valor_bolsa_anual_estimado"] = df.apply(calc_valor_bolsa, axis=1)
    
    # 8. Sanitização Ética / LGPD
    # Descarte de identificador nominal individualizado e mascaramento da matrícula
    df["matricula_mascarada"] = df["matricula"].astype(str).str.strip().apply(
        lambda m: (m[:3] + "***" + m[-2:]) if len(m) >= 6 else "***"
    )
    
    cols_silver = [
        "matricula_mascarada",
        "ano",
        "tipo_bolsa_norm",
        "linha_pesquisa_norm",
        "campus",
        "departamento_pibic_norm",
        "curso_pibic_norm",
        "perfil_social_macro",
        "cota_detalhe",
        "faixa_renda",
        "is_cotista",
        "valor_bolsa_anual_estimado",
        "orientador_norm",
        "titulo_norm",
        "status_norm",
    ]
    df_pibic_silver = df[cols_silver].copy()
    
    out_path = SILVER_DIR / "pibic_bolsistas_silver.csv"
    df_pibic_silver.to_csv(out_path, index=False, encoding="utf-8")
    logger.info(f"Salvo {out_path.name} com {len(df_pibic_silver):,} planos de pesquisa de IC tratados.")
    return df_pibic_silver


def run_silver_pipeline():
    """Executa o pipeline completo Bronze -> Silver."""
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("=== Iniciando Pipeline de Transformação (Camada Silver) ===")
    df_sigra = process_sigra()
    df_est = process_estrutura_curricular()
    df_cursos = process_cursos_graduacao()
    df_pibic = process_pibic()
    df_inep = process_inep_censo()
    logger.info("=== Camada Silver Gerada com Sucesso ===")
    return df_sigra, df_est, df_cursos, df_pibic, df_inep


if __name__ == "__main__":
    run_silver_pipeline()


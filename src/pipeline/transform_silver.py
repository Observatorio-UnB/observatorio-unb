"""
Pipeline de Transformação - Camada Bronze -> Camada Silver
Realiza limpeza, decodificação de encodings, remoção de padding,
padronização semântica, cálculo de permanência e tipagem de dados.

Lê as tabelas bronze.* e grava as silver.* no PostgreSQL, numa transação só.
"""

import bisect
import json
import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("transform_silver")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.tabelas import consultar, gravar_varias, ler, ler_bronze, tem_linhas  # noqa: E402
from src.ingestion.ckan_client import DATASETS_CONFIG, escolher_recurso  # noqa: E402

BRONZE_DIR = BASE_DIR / "data" / "bronze"
VIGENCIAS_BOLSA_IC = BRONZE_DIR / "cnpq_valor_bolsa_ic.json"


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


# Comunicação Social e Ciências Sociais eram cursos guarda-chuva; as habilitações viraram
# cursos próprios e as fontes usam os dois nomes para o mesmo curso (o catálogo tem
# 414164 "COMUNICAÇÃO SOCIAL - JORNALISMO" e 414165 "JORNALISMO"; o SIGRA, só "JORNALISMO").
PREFIXOS_GUARDA_CHUVA = re.compile(r"^(COMUNICACAO SOCIAL|CIENCIAS SOCIAIS) - ")


def normalize_curso(text: Optional[str]) -> str:
    """Nome de curso normalizado, sem o prefixo do antigo curso guarda-chuva."""
    return PREFIXOS_GUARDA_CHUVA.sub("", normalize_text(text))


def valor_bolsa_no_periodo(inicio, fim, vigencias: pd.DataFrame) -> float:
    """Soma do valor mensal em vigor em cada mês da bolsa, do mês de início ao de fim.

    vigencias: vigente_desde (AAAA-MM) e valor_mensal, em ordem. Mês anterior à primeira
    vigência fica com o primeiro valor.
    """
    inicios = [pd.Period(m, "M") for m in vigencias["vigente_desde"]]
    valores = list(vigencias["valor_mensal"])
    return sum(valores[max(bisect.bisect_right(inicios, mes) - 1, 0)]
               for mes in pd.period_range(inicio, fim, freq="M"))


def categorize_forma_saida(forma: str) -> str:
    """Classifica a forma de saída do SIGRA nas categorias comuns às duas bases de discentes.

    EVASAO é saída do curso sem diploma, inclusive por mudança de curso ou novo vestibular
    (definição de "evasão de curso" da Comissão Especial MEC/SESu, 1996). É a única definição
    que o SIGAA permite reproduzir, já que ele só marca CANCELADO, sem o motivo.
    """
    forma_norm = normalize_text(forma)
    if "FORMATURA" in forma_norm:
        return "FORMATURA"
    elif any(k in forma_norm for k in [
        "ABANDONO", "NAO CUMPRIU CONDICAO", "JUBILAMENTO", "REPR 3 VEZES", "DESLIGAMENTO",
        "NOVO VESTIBULAR", "TRANSFERENCIA", "MUDANCA DE", "DUPLA HABILITACAO", "VESTIBULAR P/",
    ]):
        return "EVASAO"
    else:
        return "OUTROS"


# Situação do vínculo no SIGAA -> categorias comuns com o SIGRA.
STATUS_SIGAA_GRUPO = {
    "CONCLUIDO": "FORMATURA",
    "FORMADO": "FORMATURA",
    "CANCELADO": "EVASAO",
    "ATIVO": "ATIVO",
    "ATIVO - FORMANDO": "ATIVO",
    "TRANCADO": "ATIVO",
}


def recurso_baixado(chave: str) -> dict:
    """O recurso do CKAN que a ingestão baixou para a fonte, a partir de bronze.ingestoes ou metadados em disco."""
    cfg = DATASETS_CONFIG[chave]
    tabela = cfg.get("tabela", "")
    try:
        df = consultar("SELECT recurso_url, baixado_em, metadados FROM bronze.ingestoes WHERE tabela = %s", (tabela,))
        if not df.empty:
            linha = df.iloc[0]
            meta = linha["metadados"]
            if meta and isinstance(meta, dict) and "resources" in meta:
                rec = escolher_recurso(meta["resources"], cfg["resource_pattern"])
                if rec:
                    return rec
            return {
                "url": str(linha["recurso_url"] or ""),
                "created": str(linha["baixado_em"] or "2024-07-01"),
            }
    except Exception:
        pass

    meta_file = BRONZE_DIR / f"metadata_{cfg['package_id']}.json"
    if meta_file.exists():
        with open(meta_file, encoding="utf-8") as f:
            recursos = json.load(f)["resources"]
        rec = escolher_recurso(recursos, cfg["resource_pattern"])
        if rec:
            return rec
    return {"url": "", "created": "2024-07-01"}


def semestre_pela_data_do_diploma(datas: pd.Series, limite: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Estima o semestre letivo de conclusão a partir da data de registro do diploma.

    O SIGAA não publica o período de saída. O registro sai logo depois do fim do semestre:
    janeiro a abril corresponde ao 2º semestre do ano anterior, maio a outubro ao 1º e
    novembro e dezembro ao 2º do próprio ano. No SIGRA, que tem as duas colunas, a regra
    acerta 94,6% dos formados (erro de 1 semestre em outros 3%).
    """
    d = pd.to_datetime(datas, format="%d/%m/%Y", errors="coerce")
    if limite is not None:
        # Diploma registrado depois da publicação do arquivo é erro de digitação (ex.: 2202).
        d = d.where(d <= limite)
    mes = d.dt.month
    ano = np.where(mes <= 4, d.dt.year - 1, d.dt.year)
    sem = np.where((mes >= 5) & (mes <= 10), 1, 2)
    return pd.DataFrame({
        "ano_saida": pd.Series(ano, index=datas.index).where(d.notna()),
        "semestre_saida": pd.Series(sem, index=datas.index).where(d.notna()),
    })


def _permanencia(df: pd.DataFrame) -> None:
    """Semestres entre o ingresso e a saída; assume ingresso no 1º semestre (a fonte só traz o ano)."""
    df["semestres_permanencia"] = 2 * \
        (df["ano_saida"] - df["ano_ingresso"]) + df["semestre_saida"]
    df["semestres_permanencia_valida"] = df["semestres_permanencia"].where(
        df["semestres_permanencia"].between(1, 30)
    )


def process_sigra() -> pd.DataFrame:
    """SIGRA (sistema legado): vínculos de graduação encerrados até a migração para o SIGAA (2020/1)."""
    logger.info("Processando bronze.sigra_discentes...")
    df = ler_bronze("bronze.sigra_discentes")

    df["nivel_norm"] = df["nivel"].apply(normalize_text)
    df = df[df["nivel_norm"] == "GRADUACAO"].copy()
    df["fonte"] = "SIGRA"
    df["departamento_norm"] = df["departamento"].apply(normalize_text)
    df["forma_saida_norm"] = df["forma_saida"].apply(normalize_text)
    df["tipo_saida_grupo"] = df["forma_saida"].apply(categorize_forma_saida)
    df = df.rename(columns={"data_registro_livro": "data_registro_diploma"})

    # periodo_saida: '20141' -> 2014/1; semestre 0 é o período de verão.
    periodo = df["periodo_saida"].astype(
        str).str.strip().str.replace(".0", "", regex=False)
    valido = periodo.str.fullmatch(r"\d{5}")
    df["ano_saida"] = pd.to_numeric(
        periodo.str[:4].where(valido), errors="coerce")
    df["semestre_saida"] = pd.to_numeric(
        periodo.str[4].where(valido), errors="coerce")
    df["periodo_saida_estimado"] = False
    return df


def process_sigaa() -> pd.DataFrame:
    """SIGAA (sistema atual): vínculos ativos na migração ou iniciados depois, com a situação atual."""
    if not tem_linhas("bronze.sigaa_discentes"):
        logger.warning("bronze.sigaa_discentes está vazia. Pulando SIGAA.")
        return pd.DataFrame()

    logger.info("Processando bronze.sigaa_discentes...")
    df = ler_bronze("bronze.sigaa_discentes")

    df["nivel_norm"] = df["nivel"].apply(normalize_text)
    df = df[df["nivel_norm"] == "GRADUACAO"].copy()
    df["fonte"] = "SIGAA"
    df = df.rename(columns={"unidade": "departamento"})
    df["departamento_norm"] = df["departamento"].apply(normalize_text)
    # A fonte formata o ano como número com separador de milhar ("2,010").
    df["ano_ingresso"] = df["ano_ingresso"].astype(str).str.replace(",", "", regex=False)
    df["sexo"] = df["sexo"].where(df["sexo"].isin(["F", "M"]))
    df["status_aluno"] = df["status_aluno"].astype(str).str.strip()
    df["tipo_saida_grupo"] = df["status_aluno"].apply(
        normalize_text).map(STATUS_SIGAA_GRUPO).fillna("OUTROS")

    formado = df["tipo_saida_grupo"] == "FORMATURA"
    rec = recurso_baixado("sigaa")
    dt_str = rec.get("created", "")[:10] or "2024-07-01"
    publicado = pd.Timestamp(dt_str)
    saida = semestre_pela_data_do_diploma(
        df["data_registro_diploma"].where(formado), limite=publicado)
    df["ano_saida"] = saida["ano_saida"]
    df["semestre_saida"] = saida["semestre_saida"]
    df["periodo_saida_estimado"] = df["ano_saida"].notna()
    return df


def process_discentes() -> pd.DataFrame:
    """Une SIGRA e SIGAA numa base única de vínculos de graduação.

    As bases se complementam: o SIGRA só tem vínculos encerrados até 2020/1, e o SIGAA os
    que estavam ativos na migração ou começaram depois. Somadas, cada coorte de ingresso
    2010-2020 fica com 9 a 13 mil discentes, sem salto na virada entre os sistemas.
    """
    df_sig = process_sigra()
    df_sigaa = process_sigaa()
    if df_sigaa.empty:
        df = df_sig
    else:
        df = pd.concat([df_sig, df_sigaa], ignore_index=True)

    df["curso_raw"] = df["curso"].astype(str).str.strip()
    df["curso_norm"] = df["curso"].apply(normalize_curso)
    df["ano_ingresso"] = pd.to_numeric(df["ano_ingresso"], errors="coerce")
    _permanencia(df)

    cols = [
        "fonte", "aluno", "nivel", "opcao", "curso", "departamento", "ano_ingresso",
        "forma_ingresso", "cota_ingresso", "data_nascimento", "sexo", "raca_cor",
        "forma_saida", "status_aluno", "data_registro_diploma", "periodo_saida",
        "nivel_norm", "curso_raw", "curso_norm", "departamento_norm", "forma_saida_norm",
        "tipo_saida_grupo", "ano_saida", "semestre_saida", "periodo_saida_estimado",
        "semestres_permanencia", "semestres_permanencia_valida",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
    df = df[cols]
    sigra_cnt = (df["fonte"] == "SIGRA").sum()
    sigaa_cnt = (df["fonte"] == "SIGAA").sum()
    logger.info(
        f"Silver unificada de discentes com {len(df):,} vínculos "
        f"({sigra_cnt:,} SIGRA + {sigaa_cnt:,} SIGAA)."
    )
    return df


GRAUS_POS_GRADUACAO = {"Mestrado", "Doutorado"}


def process_sigaa_ativos() -> pd.DataFrame:
    """Discentes de graduação ativos no semestre mais recente publicado (lista do SIGAA).

    A Bronze só tem curso, grau e período de ingresso (ver ckan_client). A lista mistura
    graduação, lato sensu (grau vazio) e pós stricto sensu; fica a graduação.
    """
    if not tem_linhas("bronze.sigaa_ativos"):
        logger.warning("bronze.sigaa_ativos está vazia. Pulando SIGAA Ativos.")
        return pd.DataFrame()

    logger.info("Processando bronze.sigaa_ativos...")
    df = ler_bronze("bronze.sigaa_ativos")
    df = df[df["grau"].notna() & ~df["grau"].isin(GRAUS_POS_GRADUACAO)].copy()

    rec = recurso_baixado("sigaa_ativos")
    arquivo = rec.get("url", "").rsplit("/", 1)[-1]
    match = re.search(r"_(\d{4})_(\d)\.csv$", arquivo)
    if match:
        ano_ref, sem_ref = map(int, match.groups())
    else:
        ano_ref, sem_ref = 2025, 1
    df["periodo_referencia"] = f"{ano_ref}/{sem_ref}"
    df["curso_norm"] = df["curso"].apply(normalize_curso)
    df["ano_ingresso"] = pd.to_numeric(df["ano_ingresso"], errors="coerce")
    df["periodo_ingresso"] = pd.to_numeric(df["periodo_ingresso"], errors="coerce")
    # Semestres cursados contando o de ingresso e o de referência; o verão (0) conta como o 1º.
    sem_ing = df["periodo_ingresso"].replace(0, 1)
    df["semestres_cursados"] = ((ano_ref - df["ano_ingresso"]) * 2 + (sem_ref - sem_ing) + 1).clip(lower=1)
    logger.info(f"Silver do SIGAA Ativos com {len(df):,} discentes de graduação ativos.")
    return df


def process_estrutura_curricular() -> pd.DataFrame:
    """Processa e consolida as matrizes curriculares da camada Bronze."""
    logger.info("Processando bronze.estrutura_curricular...")

    df = ler_bronze("bronze.estrutura_curricular")

    # 1. Normalização de textos
    df["nome_matriz_norm"] = df["nome_matriz"].apply(normalize_text)
    df["nome_curso_norm"] = df["nome_curso"].apply(normalize_curso)

    # 2. Tipagem de colunas numéricas
    cols_num = [
        "semestre_conclusao_ideal",
        "semestre_conclusao_minimo",
        "semestre_conclusao_maximo",
        "ch_total_minima",
        "cr_total_minimo",
        "ano_entrada_vigor",
    ]
    for c in cols_num:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 3. Tratamento de duplicidade de matrizes por curso
    df_clean = df.dropna(subset=["nome_curso_norm", "semestre_conclusao_ideal"]).copy()
    df_clean = df_clean.sort_values(
        by=["nome_curso_norm", "ano_entrada_vigor"],
        ascending=[True, False],
    )

    agg_dict = {
        "semestre_conclusao_ideal": "median",
        "semestre_conclusao_minimo": "min",
        "semestre_conclusao_maximo": "max",
        "ch_total_minima": "max",
        "cr_total_minimo": "max",
        "id_curso": "first",
    }
    df_consolidado = df_clean.groupby("nome_curso_norm", as_index=False).agg(agg_dict)

    logger.info(f"Silver da estrutura curricular com {len(df_consolidado):,} estruturas consolidadas.")
    return df_consolidado


def consolidar_versoes_catalogo(df: pd.DataFrame) -> pd.DataFrame:
    """Um registro por id_curso, com o valor da versão mais recente do catálogo em cada campo.

    Campo vazio na versão nova (ex.: unidade_responsavel, que saiu do arquivo em 2023) fica
    com o da última versão que o tinha. Curso que sumiu do catálogo vigente (extinto) continua,
    com no_catalogo_vigente = False: ainda tem alunos nas coortes analisadas.
    """
    df = df.replace({"NULL": np.nan, "": np.nan})
    if "publicado_em" in df.columns:
        df = df.sort_values("publicado_em", kind="stable")
        vigente = df["publicado_em"].max()
        no_vigente = set(df.loc[df["publicado_em"] == vigente, "id_curso"])
        df = df.groupby("id_curso", as_index=False, sort=False).last()
        df["no_catalogo_vigente"] = df["id_curso"].isin(no_vigente)
    else:
        df = df.groupby("id_curso", as_index=False, sort=False).last()
        df["no_catalogo_vigente"] = True

    # O formato da data mudou entre versões (2018-07-18 em 2022, 18/07/2018 depois).
    for col in ("data_funcionamento", "dou"):
        if col in df.columns:
            iso = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")
            df[col] = iso.fillna(pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")).dt.date
    return df.drop(columns=["id_servidor", "arquivo_origem", "publicado_em"], errors="ignore")


def process_cursos_graduacao() -> pd.DataFrame:
    """Processa a base de cursos de graduação, consolidando versões e metadados."""
    logger.info("Processando bronze.cursos_graduacao...")

    df_raw = ler_bronze("bronze.cursos_graduacao")
    df = consolidar_versoes_catalogo(df_raw)

    df["nome_curso_norm"] = df["nome"].apply(normalize_curso)
    df["turno_norm"] = df["turno"].apply(normalize_text)
    df["campus_norm"] = df["campus"].apply(normalize_text)
    df["grau_academico_norm"] = df["grau_academico"].apply(normalize_text)
    df["modalidade_norm"] = df["modalidade_educacao"].apply(normalize_text)

    # Tratamento de códigos de centro e datas
    df["id_curso"] = pd.to_numeric(df["id_curso"], errors="coerce")
    df["id_unidade_responsavel"] = pd.to_numeric(df["id_unidade_responsavel"], errors="coerce")
    df["id_coordenador"] = pd.to_numeric(df["id_coordenador"], errors="coerce")

    # Substituir literais NULL por NaN
    df = df.replace(["NULL", "NONE", "NAN", ""], np.nan)

    fora_vigente = (~df["no_catalogo_vigente"]).sum() if "no_catalogo_vigente" in df.columns else 0
    logger.info(f"Silver do catálogo com {len(df):,} cursos cadastrados ({fora_vigente} fora do catálogo vigente).")
    return df


# Código da UnB no cadastro de IES do INEP (Censo da Educação Superior).
CO_IES_UNB = 2


def process_inep_censo() -> pd.DataFrame:
    """
    Processa o recorte de cursos presenciais de universidades federais do Censo da Educação
    Superior (INEP), calculando as taxas por curso que permitem comparar a UnB com as demais
    federais (ver docs/fonte_inep_censo_superior.md).
    """
    if not tem_linhas("bronze.inep_censo_superior_federais"):
        logger.warning("bronze.inep_censo_superior_federais está vazia. Pulando Censo INEP.")
        return pd.DataFrame()

    logger.info("Processando bronze.inep_censo_superior_federais (Censo da Educação Superior - INEP)...")
    df = ler("bronze.inep_censo_superior_federais")

    df["curso_inep_norm"] = df["NO_CURSO"].apply(normalize_text)
    df["is_unb"] = df["CO_IES"] == CO_IES_UNB

    # Taxas do próprio Censo: a situação da matrícula é apurada no ano-censo, e não pelo
    # acompanhamento da coorte de ingresso - por isso estas taxas não são comparáveis com a
    # taxa de evasão da tabela de retenção (construída sobre as coortes de SIGRA + SIGAA).
    matriculas = df["QT_MAT"].replace(0, np.nan)
    df["taxa_trancamento_pct"] = (
        df["QT_SIT_TRANCADA"] / matriculas * 100).round(2)
    df["taxa_desvinculacao_pct"] = (
        df["QT_SIT_DESVINCULADO"] / matriculas * 100).round(2)

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

    logger.info(
        f"Silver do Censo INEP com {len(df_silver):,} cursos de federais "
        f"({int(df_silver['is_unb'].sum())} da UnB)."
    )
    return df_silver


def process_pibic() -> pd.DataFrame:
    """
    Processa a base bruta de bolsistas de iniciação científica (PIBIC/PIVIC),
    aplicando sanitização LGPD, categorização social e mapeamento territorial.
    """
    if not tem_linhas("bronze.bolsistas_iniciacao_cientifica"):
        logger.warning("bronze.bolsistas_iniciacao_cientifica está vazia. Pulando PIBIC.")
        return pd.DataFrame()

    logger.info("Processando bronze.bolsistas_iniciacao_cientifica (Iniciação Científica & Análise Social)...")
    df = ler_bronze("bronze.bolsistas_iniciacao_cientifica")

    # 1. Normalização de textos
    df["titulo_norm"] = df["titulo"].apply(normalize_text)
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

        perfil_macro = "PPI / ETNICO-RACIAL" if is_ppi else (
            "ESCOLA PUBLICA" if "ESCOLA PUB" in v else "OUTRAS COTAS")
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
    CURSO_PREFIXOS_GENERICOS = re.compile(
        r"^(BACHARELADO EM |LICENCIATURA EM |GRADUACAO EM |GRADUACAO DE |CURSO DE |CURSO )",
        flags=re.IGNORECASE,
    )

    def parse_curso_pibic(u_raw):
        if pd.isna(u_raw) or "/" not in str(u_raw):
            return ""
        part = str(u_raw).split("/", 1)[1]
        part = re.sub(r"-?\s*ALUNO:\s*\S+", "", part, flags=re.IGNORECASE)
        part = re.sub(r"-\s*FORMANDO\s*$", "", part,
                      flags=re.IGNORECASE).strip()
        part = CURSO_PREFIXOS_GENERICOS.sub("", part.strip())
        return normalize_curso(part)

    def parse_depto_pibic(u_raw):
        if pd.isna(u_raw) or "/" not in str(u_raw):
            return normalize_text(u_raw)
        return normalize_text(str(u_raw).split("/", 1)[0])

    df["curso_pibic_norm"] = df["unidade_raw"].apply(parse_curso_pibic)
    df["departamento_pibic_norm"] = df["unidade_raw"].apply(parse_depto_pibic)

    # 7. Cálculo de Investimento Público por Bolsa
    with open(VIGENCIAS_BOLSA_IC, encoding="utf-8") as f:
        vigencias = pd.DataFrame(json.load(f)["vigencias"])
    if vigencias.empty or not {"vigente_desde", "valor_mensal"} <= set(vigencias.columns):
        raise ValueError(f"{VIGENCIAS_BOLSA_IC} precisa de ao menos uma linha com vigente_desde e valor_mensal.")
    vigencias = vigencias.sort_values("vigente_desde")
    inicio = pd.to_datetime(df["inicio"], format="%d/%m/%Y", errors="coerce")
    fim = pd.to_datetime(df["fim"], format="%d/%m/%Y", errors="coerce")
    remunerada = df["tipo_bolsa_norm"] == "REMUNERADA"
    if (remunerada & (inicio.isna() | fim.isna())).any():
        raise ValueError("Bolsa remunerada sem data de início ou fim: não dá para somar o valor pago.")
    df["valor_bolsa_anual_estimado"] = [
        valor_bolsa_no_periodo(i, f, vigencias) if r else 0.0
        for i, f, r in zip(inicio, fim, remunerada)]

    cols_silver = [
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
        "titulo_norm",
        "status_norm",
    ]
    df_pibic_silver = df[cols_silver].copy()

    logger.info(f"Silver do PIBIC com {len(df_pibic_silver):,} planos de pesquisa de IC tratados.")
    return df_pibic_silver


def run_silver_pipeline():
    """Executa o pipeline completo Bronze -> Silver."""
    logger.info("=== Iniciando Pipeline de Transformação (Camada Silver) ===")
    df_discentes = process_discentes()
    df_sigaa_ativos = process_sigaa_ativos()
    df_est = process_estrutura_curricular()
    df_cursos = process_cursos_graduacao()
    df_pibic = process_pibic()
    df_inep = process_inep_censo()

    # Uma transação para a camada inteira: quem lê a silver nunca a vê pela metade.
    # O catálogo vem antes da estrutura curricular, que tem chave estrangeira para ele.
    tabelas_silver = {
        "silver.cursos_graduacao": df_cursos,
        "silver.estrutura_curricular": df_est,
        "silver.discentes_graduacao": df_discentes,
        "silver.sigaa_ativos": df_sigaa_ativos,
        "silver.pibic_bolsistas": df_pibic,
        "silver.inep_censo_superior": df_inep,
    }
    gravar_varias({k: v for k, v in tabelas_silver.items() if not v.empty})
    logger.info("=== Camada Silver Gerada com Sucesso ===")
    return df_discentes, df_est, df_cursos, df_pibic, df_inep


if __name__ == "__main__":
    run_silver_pipeline()

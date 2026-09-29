"""
Cliente de Ingestão de Dados via API CKAN 2.11 - dados.unb.br
Responsável por consultar os metadados dos pacotes e baixar os recursos
brutos de forma automatizada e reproduzível para a camada Bronze.

O arquivo baixado não vai para o disco: é lido com o dialeto da fonte (encoding e
separador, que variam entre os conjuntos do portal) e gravado em bronze.* como
texto, do jeito que veio. A procedência do download fica em bronze.ingestoes.
"""

import io
import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402
from src.db.tabelas import gravar  # noqa: E402
from src.ingestion.procedencia import registrar_ingestao  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ckan_ingestion")

BASE_URL = "https://dados.unb.br/api/3/action"

# Mapeamento de pacotes e recursos prioritários para o projeto. `resource_pattern` é uma
# regex sobre o nome do arquivo na URL; quando o portal publica uma versão nova (ex.:
# "cursos-de-graduao-08-2024.csv"), a mais recente por last_modified é a baixada.
DISCENTES_PKG = "dados-referente-aos-alunos-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado"
DATASETS_CONFIG = {
    "sigra": {
        "package_id": DISCENTES_PKG,
        "resource_pattern": r"^sigra\.csv$",
        "tabela": "bronze.sigra_discentes",
        "separador": ";",
        "encoding": "utf-8",
        "description": "Histórico acadêmico de discentes, ano de ingresso e forma/período de saída.",
    },
    "sigaa": {
        "package_id": DISCENTES_PKG,
        # Só o arquivo pseudonimizado. Os recursos SIGAA_Concluintes_* e SIGAA Ativos do mesmo
        # portal trazem nome completo e CPF parcial e ficam de fora de propósito (LGPD).
        "resource_pattern": r"^sigaa(_\d{4}(_\d)?)?\.csv$",
        "tabela": "bronze.sigaa_discentes",
        "separador": ";",
        "encoding": "utf-8",
        "description": "Discentes do SIGAA (sistema atual): situação do vínculo e registro de diploma.",
    },
    "sigaa_ativos": {
        "package_id": "lista-de-discentes-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado",
        "resource_pattern": r"^sigaa_ativos_\d{4}_\d\.csv$",
        "tabela": "bronze.sigaa_ativos",
        "separador": ";",
        "encoding": "utf-8-sig",
        # O arquivo traz nome, CPF parcial e nacionalidade. Só estas colunas são gravadas:
        # o resto é descartado em memória e nunca chega ao disco (minimização, LGPD art. 6º, III).
        "colunas": ["grau", "curso", "ano_ingresso", "periodo_ingresso"],
        "description": "Discentes ativos no semestre mais recente publicado (SIGAA), sem dado identificador.",
    },
    "estrutura_curricular": {
        "package_id": "estrutura-curricular",
        "resource_pattern": r"^estrutura-curricular.*\.csv$",
        "tabela": "bronze.estrutura_curricular",
        "separador": ";",
        "encoding": "latin-1",
        "description": "Estruturas curriculares, semestres mínimo/ideal/máximo e carga horária por curso.",
    },
    "cursos_graduacao": {
        "package_id": "cursos-de-graduacao",
        # Todas as versões (curso_graduacao.csv de 2022, cursos-de-graduao-MM-AAAA.csv depois):
        # as novas deixam de listar alguns códigos (ex.: 414162, um dos dois cadastros de
        # Comunicação Social - Jornalismo em 2022). A Silver junta tudo, com a versão mais recente valendo.
        "resource_pattern": r"^cursos?[-_](de-)?gradua\w*(-\d{2}-\d{4})?\.csv$",
        "todas_as_versoes": True,
        "tabela": "bronze.cursos_graduacao",
        "separador": ",",
        "encoding": "utf-8",
        "description": "Catálogo de cursos de graduação, turnos, campus e unidades acadêmicas responsáveis.",
    },
    "pibic": {
        "package_id": "bolsistas-de-iniciacao-cientifica",
        "resource_pattern": r"^bolsistas-de-iniciacao-cientifica.*\.csv$",
        "tabela": "bronze.bolsistas_iniciacao_cientifica",
        # O arquivo traz nome e matrícula do discente e nome do orientador. Só as colunas
        # usadas pela análise são gravadas (LGPD, art. 6º, III); os ids vêm zerados na fonte.
        "colunas": ["ano", "titulo", "tipo_de_bolsa", "linha_pesquisa", "cota",
                    "inicio", "fim", "unidade", "status"],
        "separador": ",",
        "encoding": "latin-1",
        "description": "Relação de bolsistas de Iniciação Científica (PIBIC/PIVIC), cotas sociais, bolsas remuneradas/voluntárias e linhas de pesquisa.",
    },
}


def fetch_package_metadata(package_id: str) -> Dict:
    """Consulta a API do CKAN para obter metadados completos de um pacote."""
    url = f"{BASE_URL}/package_show?id={urllib.parse.quote(package_id)}"
    logger.info(f"Consultando metadados do pacote '{package_id}'...")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "UnB-CBL-Challenge/1.0 (Data Science Agent)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if not data.get("success"):
            raise RuntimeError(
                f"Erro ao consultar pacote {package_id}: {data}")
        return data["result"]


def _data(recurso: Dict) -> str:
    # Datas ISO 8601 do CKAN ordenam corretamente como texto.
    return recurso.get("last_modified") or recurso.get("created") or ""


def recursos_casados(resources: List[Dict], pattern: str) -> List[Dict]:
    """Recursos cujo nome de arquivo casa com o padrão, do mais antigo ao mais recente.

    O portal às vezes publica o mesmo arquivo duas vezes (ex.: cursos-de-graduao-08-2024.csv
    em 23 e 24/08/2024); fica só a publicação mais recente de cada nome.
    """
    regex = re.compile(pattern, re.IGNORECASE)
    por_nome = {}
    for r in sorted(resources, key=_data):
        nome = r.get("url", "").rsplit("/", 1)[-1]
        if regex.search(nome):
            por_nome[nome] = r
    return sorted(por_nome.values(), key=_data)


def escolher_recurso(resources: List[Dict], pattern: str) -> Optional[Dict]:
    """Entre os recursos cujo nome de arquivo casa com o padrão, devolve o mais recente."""
    casados = recursos_casados(resources, pattern)
    return casados[-1] if casados else None


def download_resource(url: str) -> bytes:
    """Baixa um recurso do CKAN e devolve o conteúdo em memória."""
    logger.info(f"Baixando recurso de {url}...")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "UnB-CBL-Challenge/1.0 (Data Science Agent)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        conteudo = resp.read()
    logger.info(f"Download concluído ({len(conteudo) / (1024 * 1024):.2f} MB)")
    return conteudo


def ler_csv_bruto(conteudo: bytes, separador: str, encoding: str, colunas: Optional[List[str]] = None) -> Tuple[pd.DataFrame, int]:
    """Lê o CSV da fonte como texto, sem converter nada em nulo (bronze guarda o que veio)."""
    descartadas = 0

    def contar_bad_lines(bad_line):
        nonlocal descartadas
        descartadas += 1
        return None

    df = pd.read_csv(
        io.BytesIO(conteudo), sep=separador, encoding=encoding,
        dtype=str, keep_default_na=False, on_bad_lines=contar_bad_lines,
    )
    if descartadas > 0:
        logger.warning(f"Descartadas {descartadas} linha(s) malformada(s) durante a leitura do CSV.")
    if colunas:
        ausentes = set(colunas) - set(df.columns)
        if ausentes:
            raise RuntimeError(f"Colunas esperadas ausentes: {sorted(ausentes)}")
        df = df[colunas]
    return df, descartadas


def download_versoes(recursos: List[Dict], separador: str, encoding: str) -> Tuple[pd.DataFrame, bytes, str, int]:
    """Empilha todas as versões de um CSV num DataFrame só, marcando a origem de cada linha."""
    dfs = []
    ultimo_conteudo = b""
    ultima_url = ""
    total_descartadas = 0
    for r in recursos:
        nome = r["url"].rsplit("/", 1)[-1]
        pub = _data(r)[:10]
        logger.info(f"Baixando versão {nome} ({pub})...")
        conteudo = download_resource(r["url"])
        df, descartadas = ler_csv_bruto(conteudo, separador, encoding)
        total_descartadas += descartadas
        df["arquivo_origem"] = nome
        df["publicado_em"] = pub
        dfs.append(df)
        ultimo_conteudo = conteudo
        ultima_url = r["url"]
    df_consolidado = pd.concat(dfs, ignore_index=True)
    return df_consolidado, ultimo_conteudo, ultima_url, total_descartadas


def run_ingestion() -> Dict[str, int]:
    """
    Executa o processo completo de ingestão via API CKAN para a camada Bronze.
    Grava cada recurso em sua tabela bronze e a procedência em bronze.ingestoes.
    """
    aplicar_migracoes()
    registros_por_tabela = {}

    # Permite pular datasets via env (ex.: SKIP_DATASETS=pibic) para rodadas locais parciais.
    skip = {s.strip() for s in os.environ.get(
        "SKIP_DATASETS", "").split(",") if s.strip()}

    for key, config in DATASETS_CONFIG.items():
        if key in skip:
            logger.info(f"Pulando dataset '{key}' (SKIP_DATASETS).")
            continue
        pkg_id = config["package_id"]
        meta = fetch_package_metadata(pkg_id)

        if config.get("todas_as_versoes"):
            versoes = recursos_casados(meta.get("resources", []), config["resource_pattern"])
            if not versoes:
                raise RuntimeError(f"Nenhum recurso compatível com '{config['resource_pattern']}' em {pkg_id}")
            df, conteudo_amostra, url_amostra, descartadas = download_versoes(versoes, config["separador"], config["encoding"])
            with conectar(autocommit=True) as conn:
                with conn.transaction():
                    registros_por_tabela[config["tabela"]] = gravar(df, config["tabela"], conn=conn)
                    registrar_ingestao(
                        tabela=config["tabela"],
                        fonte="dados.unb.br",
                        recurso_url=url_amostra,
                        conteudo=conteudo_amostra,
                        encoding=config["encoding"],
                        separador=config["separador"],
                        registros=len(df),
                        pacote=pkg_id,
                        metadados=meta,
                        conn=conn,
                        linhas_descartadas=descartadas,
                    )
            continue

        target_resource = escolher_recurso(
            meta.get("resources", []), config["resource_pattern"])

        if target_resource:
            res_url = target_resource["url"]
            conteudo = download_resource(res_url)
            df, descartadas = ler_csv_bruto(conteudo, config["separador"], config["encoding"], config.get("colunas"))
            with conectar(autocommit=True) as conn:
                with conn.transaction():
                    registros_por_tabela[config["tabela"]] = gravar(df, config["tabela"], conn=conn)
                    registrar_ingestao(
                        tabela=config["tabela"],
                        fonte="dados.unb.br",
                        recurso_url=res_url,
                        conteudo=conteudo,
                        encoding=config["encoding"],
                        separador=config["separador"],
                        registros=len(df),
                        pacote=pkg_id,
                        metadados=meta,
                        conn=conn,
                        linhas_descartadas=descartadas,
                    )
        else:
            logger.warning(
                f"Recurso compatível com '{config['resource_pattern']}' não encontrado em {pkg_id}")

    logger.info("=== Ingestão da Camada Bronze Concluída com Sucesso ===")
    return registros_por_tabela


if __name__ == "__main__":
    run_ingestion()

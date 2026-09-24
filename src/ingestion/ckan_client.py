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
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
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

# Mapeamento de pacotes e recursos prioritários para o projeto. O conjunto "sigaa"
# (mesmo pacote do SIGRA) saiu da lista: nenhuma etapa do pipeline o consumia.
DATASETS_CONFIG = {
    "sigra": {
        "package_id": "dados-referente-aos-alunos-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado",
        "resource_name_pattern": "sigra.csv",
        "tabela": "bronze.sigra_discentes",
        "separador": ";",
        "encoding": "utf-8",
        "description": "Histórico acadêmico de discentes, ano de ingresso e forma/período de saída.",
    },
    "estrutura_curricular": {
        "package_id": "estrutura-curricular",
        "resource_name_pattern": "estrutura-curricular.csv",
        "tabela": "bronze.estrutura_curricular",
        "separador": ";",
        "encoding": "latin-1",
        "description": "Estruturas curriculares, semestres mínimo/ideal/máximo e carga horária por curso.",
    },
    "cursos_graduacao": {
        "package_id": "cursos-de-graduacao",
        "resource_name_pattern": "curso_graduacao.csv",
        "tabela": "bronze.cursos_graduacao",
        "separador": ",",
        "encoding": "utf-8",
        "description": "Catálogo de cursos de graduação, turnos, campus e unidades acadêmicas responsáveis.",
    },
    "pibic": {
        "package_id": "bolsistas-de-iniciacao-cientifica",
        "resource_name_pattern": "bolsistas-de-iniciacao-cientifica.csv",
        "tabela": "bronze.bolsistas_iniciacao_cientifica",
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
            raise RuntimeError(f"Erro ao consultar pacote {package_id}: {data}")
        return data["result"]


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


def ler_csv_bruto(conteudo: bytes, separador: str, encoding: str) -> pd.DataFrame:
    """Lê o CSV da fonte como texto, sem converter nada em nulo (bronze guarda o que veio)."""
    return pd.read_csv(
        io.BytesIO(conteudo), sep=separador, encoding=encoding,
        dtype=str, keep_default_na=False, on_bad_lines="skip",
    )


def run_ingestion() -> Dict[str, int]:
    """
    Executa o processo completo de ingestão via API CKAN para a camada Bronze.
    Grava cada recurso em sua tabela bronze e a procedência em bronze.ingestoes.
    """
    aplicar_migracoes()
    registros_por_tabela = {}

    # Permite pular datasets via env (ex.: SKIP_DATASETS=sigaa) — usado no CI,
    # onde 'sigaa' não é consumido por nenhuma etapa do pipeline.
    skip = {s.strip() for s in os.environ.get("SKIP_DATASETS", "").split(",") if s.strip()}

    for key, config in DATASETS_CONFIG.items():
        if key in skip:
            logger.info(f"Pulando dataset '{key}' (SKIP_DATASETS).")
            continue
        pkg_id = config["package_id"]
        meta = fetch_package_metadata(pkg_id)

        # Localiza o recurso desejado
        pattern = config["resource_name_pattern"].lower()
        target_resource = None
        for res in meta.get("resources", []):
            r_url = res.get("url", "").lower()
            r_name = res.get("name", "").lower()
            if pattern in r_url or pattern in r_name:
                target_resource = res
                break
                
        if not target_resource:
            # Se não encontrou pelo pattern exato, pega o primeiro CSV
            for res in meta.get("resources", []):
                if res.get("format", "").upper() == "CSV":
                    target_resource = res
                    break
                    
        if target_resource:
            res_url = target_resource["url"]
            conteudo = download_resource(res_url)
            df = ler_csv_bruto(conteudo, config["separador"], config["encoding"])
            registros_por_tabela[config["tabela"]] = gravar(df, config["tabela"])
            registrar_ingestao(
                tabela=config["tabela"], fonte="dados.unb.br", recurso_url=res_url, conteudo=conteudo,
                encoding=config["encoding"], separador=config["separador"], registros=len(df),
                pacote=pkg_id, metadados=meta,
            )
        else:
            logger.warning(f"Recurso compatível com '{pattern}' não encontrado em {pkg_id}")

    logger.info("=== Ingestão da Camada Bronze Concluída com Sucesso ===")
    return registros_por_tabela


if __name__ == "__main__":
    run_ingestion()

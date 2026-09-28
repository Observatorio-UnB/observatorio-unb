"""
Cliente de Ingestão de Dados via API CKAN 2.11 - dados.unb.br
Responsável por consultar os metadados dos pacotes e baixar os recursos
brutos de forma automatizada e reproduzível para a camada Bronze.
"""

import csv
import io
import json
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ckan_ingestion")

BASE_URL = "https://dados.unb.br/api/3/action"
DEFAULT_BRONZE_DIR = Path(__file__).resolve(
).parent.parent.parent / "data" / "bronze"

# Mapeamento de pacotes e recursos prioritários para o projeto. `resource_pattern` é uma
# regex sobre o nome do arquivo na URL; quando o portal publica uma versão nova (ex.:
# "cursos-de-graduao-08-2024.csv"), a mais recente por last_modified é a baixada.
DISCENTES_PKG = "dados-referente-aos-alunos-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado"
DATASETS_CONFIG = {
    "sigra": {
        "package_id": DISCENTES_PKG,
        "resource_pattern": r"^sigra\.csv$",
        "output_filename": "sigra_discentes.csv",
        "description": "Histórico acadêmico de discentes, ano de ingresso e forma/período de saída.",
    },
    "sigaa": {
        "package_id": DISCENTES_PKG,
        # Só o arquivo pseudonimizado. Os recursos SIGAA_Concluintes_* e SIGAA Ativos do mesmo
        # portal trazem nome completo e CPF parcial e ficam de fora de propósito (LGPD).
        "resource_pattern": r"^sigaa(_\d{4}(_\d)?)?\.csv$",
        "output_filename": "sigaa_discentes.csv",
        "description": "Discentes do SIGAA (sistema atual): situação do vínculo e registro de diploma.",
    },
    "sigaa_ativos": {
        "package_id": "lista-de-discentes-de-graduacao-pos-graduacao-latu-sensu-mestrado-e-doutorado",
        "resource_pattern": r"^sigaa_ativos_\d{4}_\d\.csv$",
        "output_filename": "sigaa_ativos.csv",
        # O arquivo traz nome, CPF parcial e nacionalidade. Só estas colunas são gravadas:
        # o resto é descartado em memória e nunca chega ao disco (minimização, LGPD art. 6º, III).
        "colunas": ["grau", "curso", "ano_ingresso", "periodo_ingresso"],
        "description": "Discentes ativos no semestre mais recente publicado (SIGAA), sem dado identificador.",
    },
    "estrutura_curricular": {
        "package_id": "estrutura-curricular",
        "resource_pattern": r"^estrutura-curricular.*\.csv$",
        "output_filename": "estrutura_curricular.csv",
        "description": "Estruturas curriculares, semestres mínimo/ideal/máximo e carga horária por curso.",
    },
    "cursos_graduacao": {
        "package_id": "cursos-de-graduacao",
        # Todas as versões (curso_graduacao.csv de 2022, cursos-de-graduao-MM-AAAA.csv depois):
        # as novas deixam de listar alguns códigos (ex.: 414162, um dos dois cadastros de
        # Comunicação Social - Jornalismo em 2022). A Silver junta tudo, com a versão mais recente valendo.
        "resource_pattern": r"^cursos?[-_](de-)?gradua\w*(-\d{2}-\d{4})?\.csv$",
        "todas_as_versoes": True,
        "output_filename": "cursos_graduacao.csv",
        "description": "Catálogo de cursos de graduação, turnos, campus e unidades acadêmicas responsáveis.",
    },
    "pibic": {
        "package_id": "bolsistas-de-iniciacao-cientifica",
        "resource_pattern": r"^bolsistas-de-iniciacao-cientifica.*\.csv$",
        "output_filename": "bolsistas_iniciacao_cientifica.csv",
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


def download_resource(url: str, dest_path: Path) -> Path:
    """Baixa um recurso do CKAN e salva no caminho de destino."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Baixando recurso de {url} -> {dest_path.name}...")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "UnB-CBL-Challenge/1.0 (Data Science Agent)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as f:
        bytes_copied = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            bytes_copied += len(chunk)

    size_mb = bytes_copied / (1024 * 1024)
    logger.info(f"Download concluído: {dest_path.name} ({size_mb:.2f} MB)")
    return dest_path


def download_minimizado(url: str, dest_path: Path, colunas: List[str],
                        separador: str = ";", encoding: str = "utf-8-sig") -> Path:
    """Baixa um CSV para a memória e grava só as colunas pedidas (em UTF-8, separador ",")."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Baixando recurso de {url} -> {dest_path.name} (só {', '.join(colunas)})...")
    req = urllib.request.Request(url, headers={"User-Agent": "UnB-CBL-Challenge/1.0 (Data Science Agent)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        texto = resp.read().decode(encoding)
    leitor = csv.DictReader(io.StringIO(texto, newline=""), delimiter=separador)
    ausentes = set(colunas) - set(leitor.fieldnames or [])
    if ausentes:
        raise RuntimeError(f"{url}: colunas esperadas ausentes: {sorted(ausentes)}")
    with open(dest_path, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(leitor)
    logger.info(f"Download concluído: {dest_path.name}")
    return dest_path


def download_versoes(recursos: List[Dict], dest_path: Path) -> Path:
    """Empilha todas as versões de um CSV "," num arquivo só, marcando a origem de cada linha."""
    linhas, colunas = [], []
    for r in recursos:
        nome = r["url"].rsplit("/", 1)[-1]
        logger.info(f"Baixando versão {nome} ({_data(r)[:10]})...")
        req = urllib.request.Request(r["url"], headers={"User-Agent": "UnB-CBL-Challenge/1.0 (Data Science Agent)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            leitor = csv.DictReader(io.StringIO(resp.read().decode("utf-8-sig"), newline=""))
        colunas += [c for c in leitor.fieldnames if c not in colunas]
        for linha in leitor:
            linha.update(arquivo_origem=nome, publicado_em=_data(r)[:10])
            linhas.append(linha)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas + ["arquivo_origem", "publicado_em"])
        escritor.writeheader()
        escritor.writerows(linhas)
    logger.info(f"Download concluído: {dest_path.name} ({len(recursos)} versões, {len(linhas):,} linhas)")
    return dest_path


def run_ingestion(output_dir: Optional[Path] = None) -> Dict[str, Path]:
    """
    Executa o processo completo de ingestão via API CKAN para a camada Bronze.
    Salva os metadados brutos em JSON e os arquivos CSV brutos.
    """
    out_dir = output_dir or DEFAULT_BRONZE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files = {}
    metadata_summary = {}

    # Permite pular datasets via env (ex.: SKIP_DATASETS=pibic) para rodadas locais parciais.
    skip = {s.strip() for s in os.environ.get(
        "SKIP_DATASETS", "").split(",") if s.strip()}

    for key, config in DATASETS_CONFIG.items():
        if key in skip:
            logger.info(f"Pulando dataset '{key}' (SKIP_DATASETS).")
            continue
        pkg_id = config["package_id"]
        meta = fetch_package_metadata(pkg_id)
        metadata_summary[pkg_id] = meta

        # Salva o dump de metadados brutos da API
        meta_file = out_dir / f"metadata_{pkg_id}.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        if config.get("todas_as_versoes"):
            versoes = recursos_casados(meta.get("resources", []), config["resource_pattern"])
            if not versoes:
                raise RuntimeError(f"Nenhum recurso compatível com '{config['resource_pattern']}' em {pkg_id}")
            downloaded_files[key] = download_versoes(versoes, out_dir / config["output_filename"])
            continue

        target_resource = escolher_recurso(
            meta.get("resources", []), config["resource_pattern"])

        if target_resource:
            res_url = target_resource["url"]
            dest_file = out_dir / config["output_filename"]
            if "colunas" in config:
                download_minimizado(res_url, dest_file, config["colunas"],
                                    config.get("separador", ";"), config.get("encoding", "utf-8-sig"))
            else:
                download_resource(res_url, dest_file)
            downloaded_files[key] = dest_file
        else:
            logger.warning(
                f"Recurso compatível com '{config['resource_pattern']}' não encontrado em {pkg_id}")

    logger.info("=== Ingestão da Camada Bronze Concluída com Sucesso ===")
    return downloaded_files


if __name__ == "__main__":
    run_ingestion()

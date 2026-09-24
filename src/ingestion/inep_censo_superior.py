"""
Cliente de Ingestão - Microdados do Censo da Educação Superior (INEP/MEC)

Dado público sob a Lei de Acesso à Informação (Lei 12.527/2011). Desde a LGPD
(Lei 13.709/2018) o INEP publica estes microdados agregados ao nível de IES e de curso,
sem qualquer registro individual de discente - ver docs/fonte_inep_censo_superior.md.

O arquivo bruto do INEP traz os ~253 mil cursos de graduação do Brasil (143 MB). Para a
camada Bronze é gravado apenas o recorte comparável com a UnB - cursos presenciais de
universidades públicas federais -, o que reduz o arquivo a poucos milhares de linhas.
"""

import fnmatch
import io
import logging
import ssl
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional

import certifi
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("inep_ingestion")

ANO_CENSO = 2019
ZIP_URL = f"https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_{ANO_CENSO}.zip"

# O servidor do INEP não envia o certificado intermediário da sua CA (RNP/ICPEdu), então a
# verificação TLS falha em clientes que, ao contrário dos navegadores, não buscam o
# intermediário sozinhos. A URL abaixo é a declarada no próprio certificado do servidor
# (extensão Authority Information Access) e é servida em HTTP simples.
CA_INTERMEDIARIA_URL = "http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt"

DEFAULT_BRONZE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "bronze"
OUTPUT_FILENAME = "inep_censo_superior_federais.csv"

# Filtros do recorte comparável (códigos do dicionário de dados do INEP)
CATEGORIA_PUBLICA_FEDERAL = 1
ORGANIZACAO_UNIVERSIDADE = 1
MODALIDADE_PRESENCIAL = 1

COLUNAS_CURSO = [
    "NU_ANO_CENSO",
    "CO_IES",
    "CO_CURSO",
    "NO_CURSO",
    "TP_GRAU_ACADEMICO",
    "TP_MODALIDADE_ENSINO",
    "QT_VG_TOTAL",
    "QT_INSCRITO_TOTAL",
    "QT_ING",
    "QT_MAT",
    "QT_CONC",
    "QT_SIT_TRANCADA",
    "QT_SIT_DESVINCULADO",
    "QT_SIT_TRANSFERIDO",
]
COLUNAS_IES = ["CO_IES", "NO_IES", "TP_CATEGORIA_ADMINISTRATIVA", "TP_ORGANIZACAO_ACADEMICA"]


def _montar_ca_bundle() -> Optional[str]:
    """Baixa o certificado intermediário da CA do INEP e o anexa ao bundle padrão."""
    try:
        resp = requests.get(CA_INTERMEDIARIA_URL, timeout=30)
        resp.raise_for_status()
        pem = ssl.DER_cert_to_PEM_cert(resp.content)
    except Exception as exc:
        logger.warning(f"Não foi possível obter a CA intermediária do INEP: {exc}")
        return None

    bundle = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    bundle.write(Path(certifi.where()).read_text(encoding="utf-8"))
    bundle.write("\n" + pem)
    bundle.close()
    return bundle.name


def baixar_zip_censo(url: str = ZIP_URL, tentativas: int = 4) -> bytes:
    """Baixa o pacote de microdados do INEP.

    Trata dois problemas recorrentes do servidor: a cadeia TLS incompleta (resolvida anexando
    a CA intermediária) e quedas de conexão intermitentes durante o download (resolvidas com
    novas tentativas espaçadas).
    """
    verify = True
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        try:
            resp = requests.get(url, timeout=600, verify=verify)
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.SSLError as exc:
            ultimo_erro = exc
            if verify is True:
                logger.info("Cadeia TLS do INEP incompleta; anexando a CA intermediária do certificado.")
                verify = _montar_ca_bundle()
                if not verify:
                    raise RuntimeError("Falha ao validar o certificado do servidor do INEP.") from exc
        except requests.exceptions.RequestException as exc:
            ultimo_erro = exc
            logger.warning(f"Tentativa {tentativa}/{tentativas} falhou ({type(exc).__name__}). Repetindo...")
            time.sleep(5 * tentativa)

    raise RuntimeError(f"Não foi possível baixar os microdados do INEP após {tentativas} tentativas.") from ultimo_erro


def _ler_csv_do_zip(zf: zipfile.ZipFile, padrao: str, colunas: list) -> pd.DataFrame:
    """Lê o CSV cujo nome casa com o padrão (o INEP muda o nome dos arquivos entre anos)."""
    nomes = [n for n in zf.namelist() if fnmatch.fnmatch(n.upper(), padrao)]
    if not nomes:
        raise FileNotFoundError(f"Nenhum arquivo casando com '{padrao}' no pacote do INEP.")
    with zf.open(nomes[0]) as fh:
        return pd.read_csv(
            io.BytesIO(fh.read()), sep=";", encoding="latin-1", usecols=colunas, low_memory=False
        )


def fetch_censo_superior(bronze_dir: Path = DEFAULT_BRONZE_DIR) -> Path:
    """Baixa o Censo da Educação Superior e grava o recorte de federais na camada Bronze."""
    bronze_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Baixando microdados do Censo da Educação Superior {ANO_CENSO} (INEP)...")
    conteudo = baixar_zip_censo()

    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        df_cursos = _ler_csv_do_zip(zf, "*CURSOS*.CSV", COLUNAS_CURSO)
        df_ies = _ler_csv_do_zip(zf, "*IES*.CSV", COLUNAS_IES)

    logger.info(f"Cursos de graduação no Brasil: {len(df_cursos):,}")
    df = df_cursos.merge(df_ies, on="CO_IES", how="inner")
    df = df[
        (df["TP_CATEGORIA_ADMINISTRATIVA"] == CATEGORIA_PUBLICA_FEDERAL)
        & (df["TP_ORGANIZACAO_ACADEMICA"] == ORGANIZACAO_UNIVERSIDADE)
        & (df["TP_MODALIDADE_ENSINO"] == MODALIDADE_PRESENCIAL)
    ].copy()

    out_path = bronze_dir / OUTPUT_FILENAME
    df.to_csv(out_path, index=False, encoding="utf-8")
    logger.info(
        f"Salvo {out_path.name}: {len(df):,} cursos presenciais de {df['CO_IES'].nunique()} "
        f"universidades federais."
    )
    return out_path


if __name__ == "__main__":
    fetch_censo_superior()

"""
Cliente de Ingestão - Microdados do Censo da Educação Superior (INEP/MEC)

Dado público sob a Lei de Acesso à Informação (Lei 12.527/2011). Desde a LGPD
(Lei 13.709/2018) o INEP publica estes microdados agregados ao nível de IES e de curso,
sem qualquer registro individual de discente - ver docs/fonte_inep_censo_superior.md.

O arquivo bruto do INEP traz os ~253 mil cursos de graduação do Brasil (143 MB). Para a
camada Bronze (tabela bronze.inep_censo_superior_federais) é gravado apenas o recorte
comparável com a UnB - cursos presenciais de universidades públicas federais -, o que
reduz o dado a poucos milhares de linhas.

A leitura é em streaming, com memória constante: o zip é baixado em partes para um arquivo
temporário, o CSV de cursos é lido em blocos de 50.000 linhas e cada bloco filtrado vai por
COPY para uma tabela de staging. A bronze só é trocada no fim, numa transação única.
"""

import fnmatch
import hashlib
import logging
import ssl
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Iterator, Optional, Tuple

import certifi
import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.migrar import aplicar_migracoes  # noqa: E402
from src.db.tabelas import colunas_da_tabela, copiar, preparar  # noqa: E402
from src.ingestion.procedencia import registrar_ingestao  # noqa: E402

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

TABELA_BRONZE = "bronze.inep_censo_superior_federais"
TABELA_STAGING = "pg_temp.inep_censo_staging"
LINHAS_POR_BLOCO = 50_000

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


def baixar_zip_censo(destino: Path, url: str = ZIP_URL, tentativas: int = 4) -> Tuple[int, str]:
    """Baixa o pacote de microdados do INEP em partes para `destino`; devolve (tamanho, sha256).

    Trata dois problemas recorrentes do servidor: a cadeia TLS incompleta (resolvida anexando
    a CA intermediária) e quedas de conexão intermitentes durante o download (resolvidas com
    novas tentativas espaçadas).
    """
    verify = True
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        try:
            with requests.get(url, timeout=600, verify=verify, stream=True) as resp:
                resp.raise_for_status()
                sha256, tamanho = hashlib.sha256(), 0
                with open(destino, "wb") as fh:
                    for parte in resp.iter_content(chunk_size=1 << 20):
                        fh.write(parte)
                        sha256.update(parte)
                        tamanho += len(parte)
            return tamanho, sha256.hexdigest()
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


def _abrir_csv_do_zip(zf: zipfile.ZipFile, padrao: str):
    """Abre o CSV cujo nome casa com o padrão (o INEP muda o nome dos arquivos entre anos)."""
    nomes = [n for n in zf.namelist() if fnmatch.fnmatch(n.upper(), padrao)]
    if not nomes:
        raise FileNotFoundError(f"Nenhum arquivo casando com '{padrao}' no pacote do INEP.")
    return zf.open(nomes[0])


def _ler_ies_federais(zf: zipfile.ZipFile) -> pd.DataFrame:
    """Universidades públicas federais. O arquivo de IES é pequeno (~2,6 mil linhas) e cabe inteiro."""
    with _abrir_csv_do_zip(zf, "*IES*.CSV") as fh:
        ies = pd.read_csv(fh, sep=";", encoding="latin-1", usecols=COLUNAS_IES)
    return ies[
        (ies["TP_CATEGORIA_ADMINISTRATIVA"] == CATEGORIA_PUBLICA_FEDERAL)
        & (ies["TP_ORGANIZACAO_ACADEMICA"] == ORGANIZACAO_UNIVERSIDADE)
    ]


def ler_cursos_em_blocos(zf: zipfile.ZipFile, linhas_por_bloco: int = LINHAS_POR_BLOCO) -> Iterator[pd.DataFrame]:
    """Lê o CSV de cursos direto do zip, um bloco por vez: só um bloco fica em memória."""
    with _abrir_csv_do_zip(zf, "*CURSOS*.CSV") as fh:
        yield from pd.read_csv(fh, sep=";", encoding="latin-1", usecols=COLUNAS_CURSO, chunksize=linhas_por_bloco)


def recortar_federais(bloco: pd.DataFrame, ies_federais: pd.DataFrame) -> pd.DataFrame:
    """Cursos presenciais de universidades públicas federais dentro de um bloco."""
    presenciais = bloco[bloco["TP_MODALIDADE_ENSINO"] == MODALIDADE_PRESENCIAL]
    return presenciais.merge(ies_federais, on="CO_IES", how="inner")


def fetch_censo_superior() -> int:
    """Baixa o Censo da Educação Superior e grava o recorte de federais na camada Bronze."""
    aplicar_migracoes()
    logger.info(f"Baixando microdados do Censo da Educação Superior {ANO_CENSO} (INEP)...")

    with tempfile.TemporaryDirectory() as pasta:
        arquivo_zip = Path(pasta) / "censo.zip"
        tamanho, sha256 = baixar_zip_censo(arquivo_zip)
        logger.info(f"Download concluído ({tamanho / 1e6:.1f} MB).")

        with zipfile.ZipFile(arquivo_zip) as zf, conectar(autocommit=True) as conn:
            ies_federais = _ler_ies_federais(zf)
            colunas = colunas_da_tabela(conn, TABELA_BRONZE)
            # Staging: os blocos entram aqui; a bronze só muda no fim, numa transação única.
            conn.execute(f"CREATE TEMP TABLE {TABELA_STAGING.split('.')[1]} "
                         f"(LIKE {TABELA_BRONZE} INCLUDING DEFAULTS)")

            inicio = time.monotonic()
            lidas = gravadas = 0
            universidades = set()
            for numero, bloco in enumerate(ler_cursos_em_blocos(zf), start=1):
                recorte = recortar_federais(bloco, ies_federais)
                recorte = recorte.assign(_ordem=range(gravadas + 1, gravadas + len(recorte) + 1))
                copiar(conn, TABELA_STAGING, preparar(recorte, colunas, TABELA_BRONZE))
                lidas += len(bloco)
                gravadas += len(recorte)
                universidades.update(recorte["CO_IES"])
                decorrido = time.monotonic() - inicio
                logger.info(f"Bloco {numero}: {lidas:,} linhas lidas, {gravadas:,} no recorte "
                            f"({lidas / decorrido:,.0f} linhas/s).")

            with conn.transaction():
                conn.execute(f"TRUNCATE {TABELA_BRONZE}")
                conn.execute(f"INSERT INTO {TABELA_BRONZE} SELECT * FROM {TABELA_STAGING}")
                # O CSV do INEP vem dentro de um zip: o encoding (latin-1) é o declarado pelo INEP, não verificado.
                registrar_ingestao(
                    tabela=TABELA_BRONZE, fonte="INEP", recurso_url=ZIP_URL, conteudo=None,
                    tamanho_bytes=tamanho, sha256=sha256, encoding="latin-1", separador=";",
                    registros=gravadas, verificar_encoding=False, conn=conn,
                )
            conn.execute(f"ANALYZE {TABELA_BRONZE}")

    decorrido = time.monotonic() - inicio
    logger.info(f"Cursos de graduação no Brasil: {lidas:,} em {decorrido:.1f} s ({lidas / decorrido:,.0f} linhas/s).")
    logger.info(
        f"Gravados em {TABELA_BRONZE}: {gravadas:,} cursos presenciais de {len(universidades)} "
        f"universidades federais."
    )
    return gravadas


if __name__ == "__main__":
    fetch_censo_superior()

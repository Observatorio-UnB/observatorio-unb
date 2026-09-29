"""
Procedência dos arquivos baixados, registrada em bronze.ingestoes.

Sem o arquivo bruto em disco, este registro é a evidência de onde o dado veio,
com que encoding e separador foi lido e se a fonte mudou (sha256). A auditoria
de qualidade (src/audit/quality_auditor.py) lê daqui o achado de encoding.
"""

import hashlib
import json
import logging
from typing import Dict, Optional, Tuple

import psycopg

from src.db.conexao import conectar

logger = logging.getLogger("procedencia")

# A auditoria original conferia as 15 primeiras linhas do arquivo.
LINHAS_VERIFICADAS = 15


def verificar_utf8(conteudo: bytes) -> Tuple[bool, Optional[int], Optional[str]]:
    """(é UTF-8 válido, primeira linha inválida, evidência) nas primeiras linhas do arquivo."""
    for numero, linha in enumerate(conteudo[:1_000_000].splitlines()[:LINHAS_VERIFICADAS], start=1):
        try:
            linha.decode("utf-8")
        except UnicodeDecodeError as erro:
            return False, numero, f"Byte {hex(linha[erro.start])} inválido em UTF-8: {linha[:80]}"
    return True, None, None


def registrar_ingestao(
    tabela: str,
    fonte: str,
    recurso_url: str,
    conteudo: bytes,
    encoding: str,
    separador: str,
    registros: int,
    pacote: Optional[str] = None,
    metadados: Optional[Dict] = None,
    verificar_encoding: bool = True,
    conn: Optional[psycopg.Connection] = None,
    linhas_descartadas: int = 0,
) -> None:
    utf8_valido, linha_invalida, evidencia = (
        verificar_utf8(conteudo) if verificar_encoding else (None, None, None)
    )
    if utf8_valido and encoding.lower().startswith("latin"):
        logger.warning(
            f"{tabela}: o arquivo tem conteúdo compatível com UTF-8, mas o encoding configurado é '{encoding}'. "
            "Se a fonte passou a publicar em UTF-8, o texto pode ter acentos trocados."
        )

    sql_insert = """
        INSERT INTO bronze.ingestoes
          (tabela, fonte, pacote, recurso_url, baixado_em, tamanho_bytes, sha256, encoding, separador,
           registros, linhas_descartadas, utf8_valido, linha_invalida, evidencia_encoding, metadados)
        VALUES (%s, %s, %s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tabela) DO UPDATE SET
          fonte = EXCLUDED.fonte, pacote = EXCLUDED.pacote, recurso_url = EXCLUDED.recurso_url,
          baixado_em = EXCLUDED.baixado_em, tamanho_bytes = EXCLUDED.tamanho_bytes,
          sha256 = EXCLUDED.sha256, encoding = EXCLUDED.encoding, separador = EXCLUDED.separador,
          registros = EXCLUDED.registros, linhas_descartadas = EXCLUDED.linhas_descartadas,
          utf8_valido = EXCLUDED.utf8_valido, linha_invalida = EXCLUDED.linha_invalida,
          evidencia_encoding = EXCLUDED.evidencia_encoding, metadados = EXCLUDED.metadados
    """
    params = (
        tabela, fonte, pacote, recurso_url, len(conteudo), hashlib.sha256(conteudo).hexdigest(),
        encoding, separador, registros, linhas_descartadas, utf8_valido, linha_invalida, evidencia,
        json.dumps(metadados, ensure_ascii=False) if metadados is not None else None,
    )

    if conn is not None:
        conn.execute(sql_insert, params)
    else:
        with conectar() as c:
            c.execute(sql_insert, params)

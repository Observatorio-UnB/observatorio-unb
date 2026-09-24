"""
Procedência dos arquivos baixados, registrada em bronze.ingestoes.

Sem o arquivo bruto em disco, este registro é a evidência de onde o dado veio,
com que encoding e separador foi lido e se a fonte mudou (sha256). A auditoria
de qualidade (src/audit/quality_auditor.py) lê daqui o achado de encoding.
"""

import hashlib
import json
from typing import Dict, Optional, Tuple

from src.db.conexao import conectar

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
) -> None:
    utf8_valido, linha_invalida, evidencia = (
        verificar_utf8(conteudo) if verificar_encoding else (None, None, None)
    )
    with conectar() as conn:
        conn.execute(
            """
            INSERT INTO bronze.ingestoes
              (tabela, fonte, pacote, recurso_url, baixado_em, tamanho_bytes, sha256, encoding, separador,
               registros, utf8_valido, linha_invalida, evidencia_encoding, metadados)
            VALUES (%s, %s, %s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tabela) DO UPDATE SET
              fonte = EXCLUDED.fonte, pacote = EXCLUDED.pacote, recurso_url = EXCLUDED.recurso_url,
              baixado_em = EXCLUDED.baixado_em, tamanho_bytes = EXCLUDED.tamanho_bytes,
              sha256 = EXCLUDED.sha256, encoding = EXCLUDED.encoding, separador = EXCLUDED.separador,
              registros = EXCLUDED.registros, utf8_valido = EXCLUDED.utf8_valido,
              linha_invalida = EXCLUDED.linha_invalida, evidencia_encoding = EXCLUDED.evidencia_encoding,
              metadados = EXCLUDED.metadados
            """,
            (
                tabela, fonte, pacote, recurso_url, len(conteudo), hashlib.sha256(conteudo).hexdigest(),
                encoding, separador, registros, utf8_valido, linha_invalida, evidencia,
                json.dumps(metadados, ensure_ascii=False) if metadados is not None else None,
            ),
        )

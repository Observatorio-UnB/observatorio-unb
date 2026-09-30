"""
Cliente HTTP mínimo da API pública do Supabase (PostgREST e Edge Functions).

É como o painel publicado no GitHub Pages lê a gold e faz a busca semântica: o stlite roda
no navegador e não abre conexão com o PostgreSQL. Só usa a chave pública (`anon`/publishable);
as funções que ela alcança estão em db/migrations/0018_api_publica_supabase.sql.

A configuração vem de SUPABASE_URL e SUPABASE_ANON_KEY (ambiente) ou, no navegador, de
supabase_config.json na raiz do filesystem virtual (gerado pelo CI a partir das variáveis do
repositório, ver site/index.html). Sem configuração, `configurado()` é False e o painel cai
no banco local ou no export estático.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_NAVEGADOR = BASE_DIR / "supabase_config.json"
TIMEOUT_S = 30


class ErroSupabase(RuntimeError):
    pass


def _config() -> Tuple[str, str]:
    url, chave = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_ANON_KEY", "")
    if not (url and chave) and CONFIG_NAVEGADOR.exists():
        dados = json.loads(CONFIG_NAVEGADOR.read_text(encoding="utf-8"))
        url, chave = dados.get("url", ""), dados.get("anon_key", "")
    return url.rstrip("/"), chave


def configurado() -> bool:
    url, chave = _config()
    return bool(url and chave)


def _cabecalhos(chave: str) -> Dict[str, str]:
    cabecalhos = {"apikey": chave, "Content-Type": "application/json"}
    # A chave legada é um JWT e também vai em Authorization; a publishable (sb_publishable_...)
    # não é JWT e só vai em apikey.
    if chave.startswith("eyJ"):
        cabecalhos["Authorization"] = f"Bearer {chave}"
    return cabecalhos


def _post(url: str, cabecalhos: Dict[str, str], corpo: str) -> Tuple[int, str]:
    if sys.platform == "emscripten":
        # stlite (Pyodide) roda num Web Worker, onde XMLHttpRequest síncrono é permitido.
        # urllib não funciona no navegador e o script do Streamlit não é assíncrono.
        from js import XMLHttpRequest  # type: ignore[import-not-found]

        xhr = XMLHttpRequest.new()
        xhr.open("POST", url, False)
        xhr.timeout = TIMEOUT_S * 1000  # estourar vira exceção e o painel cai no export estático
        for nome, valor in cabecalhos.items():
            xhr.setRequestHeader(nome, valor)
        xhr.send(corpo)
        return int(xhr.status), str(xhr.responseText)

    import urllib.error
    import urllib.request

    pedido = urllib.request.Request(url, data=corpo.encode("utf-8"), headers=cabecalhos, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as resposta:
            return resposta.status, resposta.read().decode("utf-8")
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read().decode("utf-8", errors="replace")


def _chamar(caminho: str, corpo: Optional[Dict]) -> Any:
    url, chave = _config()
    if not (url and chave):
        raise ErroSupabase("Supabase não configurado (SUPABASE_URL e SUPABASE_ANON_KEY).")
    status, texto = _post(f"{url}{caminho}", _cabecalhos(chave), json.dumps(corpo or {}))
    if status < 200 or status >= 300:
        raise ErroSupabase(f"HTTP {status} em {caminho}: {texto[:300]}")
    return json.loads(texto)


def rpc(nome: str, corpo: Optional[Dict] = None) -> Any:
    """Chama uma função do PostgreSQL exposta em public (POST /rest/v1/rpc/<nome>)."""
    return _chamar(f"/rest/v1/rpc/{nome}", corpo)


def funcao(nome: str, corpo: Optional[Dict] = None) -> Any:
    """Chama uma Edge Function (POST /functions/v1/<nome>)."""
    return _chamar(f"/functions/v1/{nome}", corpo)

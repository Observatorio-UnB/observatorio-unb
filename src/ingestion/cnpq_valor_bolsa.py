"""
Cliente de Ingestão - Valor mensal da bolsa de Iniciação Científica (IC) do CNPq

O CNPq só publica a tabela de valores vigente, sem histórico. A tabela de vigências
(data/bronze/cnpq_valor_bolsa_ic.json, versionada no git) guarda um valor por linha, com o
mês a partir do qual vale. A cada execução, uma requisição lê o valor atual da página
oficial; se ele mudou, entra uma linha nova valendo desde o mês da leitura.

O histórico anterior à automação (R$ 400 desde jul/2012, R$ 700 desde fev/2023) foi
conferido nas cópias da mesma página no Internet Archive (links na coluna fonte).
"""

import html
import json
import logging
import re
from datetime import date
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cnpq_valor_bolsa")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
VIGENCIAS = BASE_DIR / "data" / "bronze" / "cnpq_valor_bolsa_ic.json"
PAGINA = "https://www.gov.br/cnpq/pt-br/acesso-a-informacao/bolsas-e-auxilios/copy_of_modalidades/tabela-de-valores-no-pais"
VALOR_IC = re.compile(r"Inicia[çc][ãa]o Cient[íi]fica\s*(?:\(PIBIC\)\s*)?IC\s*-?\s*([\d.]+,\d{2})")


def valor_ic(pagina_html: str):
    """Valor mensal da IC (float) na tabela de valores, ou None se a página não tiver a linha."""
    texto = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", pagina_html)))
    m = VALOR_IC.search(texto)
    return float(m.group(1).replace(".", "").replace(",", ".")) if m else None


def run():
    with open(VIGENCIAS, encoding="utf-8") as f:
        dados = json.load(f)
    vigencias = dados["vigencias"]

    r = requests.get(PAGINA, timeout=60, headers={"User-Agent": "observatorio-unb"})
    r.raise_for_status()
    valor = valor_ic(r.text)
    if valor is None:
        raise RuntimeError("A tabela do CNPq não tem mais a linha de Iniciação Científica; revisar VALOR_IC.")

    if valor == vigencias[-1]["valor_mensal"]:
        logger.info(f"Bolsa IC sem mudança: R$ {valor:,.2f}.")
        return
    vigencias.append({"vigente_desde": date.today().strftime("%Y-%m"), "valor_mensal": valor,
                      "fonte": f"{PAGINA} (lida em {date.today().isoformat()})"})
    with open(VIGENCIAS, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)
    logger.info(f"Novo valor da bolsa IC: R$ {valor:,.2f}, desde {vigencias[-1]['vigente_desde']}.")


if __name__ == "__main__":
    run()

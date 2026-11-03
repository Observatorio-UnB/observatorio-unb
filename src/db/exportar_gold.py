"""
Exporta a camada gold do banco para um JSON estático (export/gold.json).

É o que a versão do painel no GitHub Pages lê: o stlite roda o Python no navegador
de quem visita, sem acesso ao banco. O arquivo é gerado pelo CI a cada publicação,
a partir do banco, e não é versionado. Só entra a gold (agregada, k >= 5).

O painel local usa a mesma função (montar_snapshot) lendo do banco, então as duas
versões montam os dados pelo mesmo caminho.

Uso:
    python3 src/db/exportar_gold.py                 # grava export/gold.json
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402
from src.db.frescor import resumo_para_o_painel  # noqa: E402
from src.db.tabelas import consultar, ler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("exportar_gold")

SAIDA = BASE_DIR / "export" / "gold.json"
TABELAS = (
    "gold.retencao_cursos_unb",
    "gold.ativos_hoje_cursos_unb",
    "gold.pibic_social_unb",
    "gold.regras_harmonizacao_canonicas",
    "gold.inep_benchmark_cursos_unb",
    # Tabela de consumo da camada transformada (dbt), que responde à pergunta da E1 no painel.
    "dbt_marts.painel_cursos_criticos",
)


def montar_snapshot() -> Dict:
    """Tabelas e relatórios da gold, como registros JSON, na ordem em que foram gravados."""
    tabelas = {}
    for tabela in TABELAS:
        try:
            df = ler(tabela)
            tabelas[tabela.split(".")[1]] = json.loads(df.to_json(orient="records", force_ascii=False))
        except Exception:
            tabelas[tabela.split(".")[1]] = []
    try:
        relatorios = dict(consultar("SELECT nome, conteudo FROM gold.relatorios ORDER BY nome").values.tolist())
    except Exception:
        relatorios = {}
    # Atualização da view do painel e SLA (docs/frescor_sla.md). O painel calcula a idade na hora
    # em que é aberto, então a versão do GitHub Pages mostra quando o export envelheceu.
    try:
        with conectar() as conn:
            frescor = resumo_para_o_painel(conn)
    except Exception:
        frescor = None
    # Quando a gold foi gravada pela última vez, para o painel mostrar a idade dos dados.
    try:
        carregado_em = consultar("SELECT max(_carregado_em) AS carregado_em FROM gold.relatorios").iloc[0]["carregado_em"]
        carregado_em = carregado_em.isoformat(timespec="seconds") if carregado_em is not None else None
    except Exception:
        carregado_em = None
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tabelas": tabelas,
        "relatorios": relatorios,
        "frescor": frescor,
        "carregado_em": carregado_em,
    }


def exportar(saida: Path = SAIDA) -> Path:
    snapshot = montar_snapshot()
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    linhas = {nome: len(registros) for nome, registros in snapshot["tabelas"].items()}
    logger.info(f"Gold exportada para {saida.relative_to(BASE_DIR)}: {linhas}")
    return saida


if __name__ == "__main__":
    exportar()

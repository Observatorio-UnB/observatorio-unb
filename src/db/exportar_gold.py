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
    "gold.pibic_social_unb",
    "gold.regras_harmonizacao_canonicas",
    "gold.inep_benchmark_cursos_unb",
)


def montar_snapshot() -> Dict:
    """Tabelas e relatórios da gold, como registros JSON, na ordem em que foram gravados."""
    tabelas = {
        # to_json converte NaN em null e tipos do numpy em tipos JSON.
        tabela.split(".")[1]: json.loads(ler(tabela).to_json(orient="records", force_ascii=False))
        for tabela in TABELAS
    }
    relatorios = dict(consultar("SELECT nome, conteudo FROM gold.relatorios ORDER BY nome").values.tolist())
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tabelas": tabelas,
        "relatorios": relatorios,
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

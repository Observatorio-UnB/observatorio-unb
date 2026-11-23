"""
Frescor e SLA da tabela de consumo do painel, gold.mv_dashboard_executivo.

Duas verificações, com o mesmo SLA de 35 dias: a atualização mensal roda no dia 1 de cada mês
(.github/workflows/atualiza-dados.yml), e os 4 dias a mais são o prazo para corrigir uma falha.

  - processamento: idade da view, now() - max(gerado_em). Diz se o pipeline está rodando. Só
    precisa da gold, então vale para o banco local e para o Supabase.
  - fonte (--fonte, consulta o portal): para cada arquivo do portal que alimenta a view, a versão
    mais recente publicada (last_modified no CKAN, escolhida como na ingestão). Publicada depois
    da última atualização da view, ela está pendente, e viola o SLA quando passa de 35 dias.

A idade do dado na origem não entra no SLA: o portal publica raramente (o extrato do SIGAA é de
07/2024), e isso não depende do pipeline. O SLA cobre o que o projeto controla.

Sai com código 1 quando alguma verificação viola o SLA.

Uso:
    python3 src/db/frescor.py                                   # banco local (DATABASE_URL)
    python3 src/db/frescor.py --fonte                           # e as publicações do portal
    python3 src/db/frescor.py --banco "$SUPABASE_DATABASE_URL" --fonte
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import psycopg

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
from src.db.conexao import conectar  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("frescor")

TABELA = "gold.mv_dashboard_executivo"
SLA_DIAS = 35

# Arquivos do portal (chaves de DATASETS_CONFIG em src/ingestion/ckan_client.py) que chegam à view:
# vínculos e ativos (retenção e ativos hoje), matriz curricular e catálogo de cursos.
FONTES_DA_VIEW = ("sigra", "sigaa", "sigaa_ativos", "estrutura_curricular", "cursos_graduacao")


@dataclass
class Verificacao:
    nome: str
    dias: float
    limite_dias: int
    detalhe: str

    @property
    def ok(self) -> bool:
        return self.dias <= self.limite_dias


def atualizacao_da_view(conn: psycopg.Connection) -> datetime:
    """Momento do último REFRESH da view (gerado_em é o now() do refresh)."""
    atualizada_em = conn.execute(f"SELECT max(gerado_em) FROM {TABELA}").fetchone()[0]
    if atualizada_em is None:
        raise RuntimeError(f"{TABELA} vazia: rode o pipeline (bash scripts/rodar_pipeline.sh).")
    return atualizada_em


def _dias(intervalo) -> float:
    # Sem arredondar: 35 dias e 1 hora já passam de 35 dias. O arredondamento é só na saída.
    return intervalo.total_seconds() / 86_400


def verificar_processamento(atualizada_em: datetime, agora: datetime, sla_dias: int = SLA_DIAS) -> Verificacao:
    return Verificacao(
        nome=f"processamento ({TABELA})",
        dias=max(_dias(agora - atualizada_em), 0.0),
        limite_dias=sla_dias,
        detalhe=f"view atualizada em {atualizada_em:%d/%m/%Y %H:%M} UTC",
    )


def verificar_fonte(atualizada_em: datetime, publicacoes: Dict[str, datetime], agora: datetime,
                    sla_dias: int = SLA_DIAS) -> List[Verificacao]:
    """Uma verificação por arquivo: dias desde uma publicação que a view ainda não processou."""
    verificacoes = []
    for fonte, publicada_em in publicacoes.items():
        if publicada_em <= atualizada_em:
            dias, detalhe = 0.0, f"publicado em {publicada_em:%d/%m/%Y}, já processado"
        else:
            dias = _dias(agora - publicada_em)
            detalhe = f"publicado em {publicada_em:%d/%m/%Y}, depois da última atualização da view"
        verificacoes.append(Verificacao(f"fonte ({fonte})", dias, sla_dias, detalhe))
    return verificacoes


def _como_utc(texto: str) -> datetime:
    # O CKAN devolve last_modified em UTC, sem fuso.
    data = datetime.fromisoformat(texto)
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def publicacoes_do_portal(fontes=FONTES_DA_VIEW) -> Dict[str, datetime]:
    """Publicação do arquivo que a ingestão escolheria hoje, por fonte."""
    from src.ingestion.ckan_client import DATASETS_CONFIG, _data, escolher_recurso, fetch_package_metadata

    pacotes: Dict[str, Dict] = {}
    publicacoes = {}
    for fonte in fontes:
        config = DATASETS_CONFIG[fonte]
        if config["package_id"] not in pacotes:
            pacotes[config["package_id"]] = fetch_package_metadata(config["package_id"])
        recurso = escolher_recurso(pacotes[config["package_id"]].get("resources", []), config["resource_pattern"])
        if recurso is None:
            raise RuntimeError(f"Nenhum recurso de '{fonte}' casa com {config['resource_pattern']} no portal.")
        publicacoes[fonte] = _como_utc(_data(recurso))
    return publicacoes


def resumo_para_o_painel(conn: psycopg.Connection) -> Optional[Dict]:
    """Atualização da view e SLA, para o painel calcular a idade na hora em que é aberto."""
    try:
        atualizada_em = atualizacao_da_view(conn)
    except (RuntimeError, psycopg.Error):
        return None
    return {"tabela": TABELA, "atualizada_em": atualizada_em.isoformat(timespec="seconds"), "sla_dias": SLA_DIAS}


def verificar(url: Optional[str] = None, fonte: bool = False, sla_dias: int = SLA_DIAS,
              agora: Optional[datetime] = None) -> List[Verificacao]:
    agora = agora or datetime.now(timezone.utc)
    with conectar(url) as conn:
        atualizada_em = atualizacao_da_view(conn)
    verificacoes = [verificar_processamento(atualizada_em, agora, sla_dias)]
    if fonte:
        verificacoes += verificar_fonte(atualizada_em, publicacoes_do_portal(), agora, sla_dias)
    return verificacoes


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--banco", help="URL do banco (padrão: DATABASE_URL)")
    parser.add_argument("--fonte", action="store_true", help="conferir também as publicações do portal")
    parser.add_argument("--sla-dias", type=int, default=SLA_DIAS)
    args = parser.parse_args(argv)

    verificacoes = verificar(args.banco, args.fonte, args.sla_dias)
    for v in verificacoes:
        nivel = logging.INFO if v.ok else logging.ERROR
        logger.log(nivel, f"{'OK  ' if v.ok else 'VIOLADO'} {v.nome}: {v.dias:.1f} de {v.limite_dias} dias ({v.detalhe})")
    violadas = [v for v in verificacoes if not v.ok]
    if violadas:
        logger.error(f"SLA de frescor violado em {len(violadas)} verificação(ões). Ver docs/frescor_sla.md.")
        return 1
    logger.info(f"SLA de frescor cumprido ({len(verificacoes)} verificação(ões)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

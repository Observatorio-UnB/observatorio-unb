"""
Resposta do painel à pergunta de gestão da E1 (docs/challenge_canvas.md), sem Streamlit.

O ranking vem de dbt_marts.painel_cursos_criticos, a tabela de consumo da camada transformada
(transform/, ADR 0029). Sem ela (banco sem as camadas do dbt, ou export antigo), o ranking sai de
gold.retencao_cursos_unb, com o mesmo IRC (a reconciliação do dbt garante que os dois batem).

Fica num módulo próprio para ser testado sem subir o painel (tests/test_unit_resposta_e1.py) e
para rodar igual no GitHub Pages, onde o stlite carrega este arquivo junto com o app.py.
"""

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

PERGUNTA_E1 = (
    "Em quais cursos a taxa de retenção e atraso na integralização curricular é mais crítica, "
    "demandando intervenções institucionais prioritárias?"
)

# Mesmo SLA de frescor do pipeline: atualização no dia 1 de cada mês e 4 dias de folga.
SLA_DIAS = 35

FONTE_DBT = "dbt_marts.painel_cursos_criticos (camada transformada, dbt)"
FONTE_GOLD = "gold.retencao_cursos_unb (sem a camada transformada nestes dados)"

COLUNAS = {
    "posicao": "Posição",
    "nome_curso": "Curso",
    "campus": "Campus",
    "classificacao_retencao": "Classificação",
    "indice_retencao_critica": "IRC",
    "taxa_evasao_pct": "Evasão (%)",
    "atraso_medio_semestres": "Atraso médio (sem.)",
    "formados_tempo_ideal_pct": "Formados no prazo ideal (%)",
    "total_ingressantes": "Ingressantes",
}


def ranking_cursos_criticos(tabelas: Dict[str, List[Dict]], df_gold: Optional[pd.DataFrame],
                            cursos_tronco: Iterable[str] = ()) -> Tuple[Optional[pd.DataFrame], str]:
    """Cursos terminais na ordem do IRC (posição 1 = mais crítico) e a tabela de onde vieram."""
    painel = tabelas.get("painel_cursos_criticos") or []
    if painel:
        df = pd.DataFrame(painel).sort_values(["posicao", "nome_curso"])
        return df[list(COLUNAS)].reset_index(drop=True), FONTE_DBT

    if df_gold is None or df_gold.empty:
        return None, FONTE_GOLD
    # Mesma regra do mart: sem os cursos-tronco (ADR 0022), posição pelo IRC, empate divide a posição.
    df = df_gold[~df_gold["curso"].isin(set(cursos_tronco))].rename(columns={
        "curso": "nome_curso",
        "desvio_medio_semestres": "atraso_medio_semestres",
        "total_discentes_registrados": "total_ingressantes",
    })
    df = df.assign(posicao=df["indice_retencao_critica"].rank(method="min", ascending=False).astype(int))
    df = df.sort_values(["posicao", "nome_curso"])
    return df[list(COLUNAS)].reset_index(drop=True), FONTE_GOLD


def frescor(carregado_em: Optional[str], agora: Optional[datetime] = None) -> Optional[Tuple[datetime, int, bool]]:
    """(data da carga, idade em dias, dentro do SLA). A idade conta até agora, e não até o export."""
    if not carregado_em:
        return None
    data = datetime.fromisoformat(carregado_em)
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    idade = (agora or datetime.now(timezone.utc)) - data
    return data, idade.days, idade.total_seconds() <= SLA_DIAS * 86_400

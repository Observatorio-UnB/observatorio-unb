"""
Resposta do painel à pergunta de gestão da E1 (docs/challenge_canvas.md), sem Streamlit.

O ranking vem de dbt_marts.painel_cursos_criticos, a tabela de consumo da camada transformada
(transform/, ADR 0029). Sem ela (banco sem as camadas do dbt, ou export antigo), o ranking sai de
gold.retencao_cursos_unb, com o mesmo IRC. O mart também é descartado quando não bate com a gold da
carga atual: se o pipeline rodou sem o dbt, o mart que ficou no banco é de uma carga anterior, e a
data de frescor exibida (a da gold) não valeria para ele.

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
FONTE_GOLD_MART_ANTIGO = "gold.retencao_cursos_unb (o mart do dbt não bate com a carga atual da gold)"

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
    tem_gold = df_gold is not None and not df_gold.empty
    if painel:
        df = pd.DataFrame(painel).sort_values(["posicao", "nome_curso"])
        if not tem_gold or _mesma_carga(df, df_gold, cursos_tronco):
            return df[list(COLUNAS)].reset_index(drop=True), FONTE_DBT
        fonte = FONTE_GOLD_MART_ANTIGO
    else:
        fonte = FONTE_GOLD

    if not tem_gold:
        return None, fonte
    # Mesma regra do mart: sem os cursos-tronco (ADR 0022), posição pelo IRC, empate divide a posição.
    df = df_gold[~df_gold["curso"].isin(set(cursos_tronco))].rename(columns={
        "curso": "nome_curso",
        "desvio_medio_semestres": "atraso_medio_semestres",
        "total_discentes_registrados": "total_ingressantes",
    })
    df = df.assign(posicao=df["indice_retencao_critica"].rank(method="min", ascending=False).astype(int))
    df = df.sort_values(["posicao", "nome_curso"])
    return df[list(COLUNAS)].reset_index(drop=True), fonte


def _mesma_carga(painel: pd.DataFrame, df_gold: pd.DataFrame, cursos_tronco: Iterable[str]) -> bool:
    """O mart e a gold têm os mesmos cursos com o mesmo IRC: vêm da mesma carga. O IRC é comparado
    com uma casa, a precisão em que os dois o gravam; as taxas podem diferir no arredondamento."""
    terminais = df_gold[~df_gold["curso"].isin(set(cursos_tronco))]
    def irc(nomes, valores):
        return set(zip(nomes, valores.astype(float).round(1)))
    return irc(painel["nome_curso"], painel["indice_retencao_critica"]) == \
        irc(terminais["curso"], terminais["indice_retencao_critica"])


def frescor(carregado_em: Optional[str], agora: Optional[datetime] = None) -> Optional[Tuple[datetime, int, bool]]:
    """(data da carga, idade em dias, dentro do SLA). A idade conta até agora, e não até o export.

    carregado_em vem de gold.relatorios._carregado_em, um timestamptz, então a string já traz o fuso.
    Sem fuso (dado de outra origem), vale UTC: no pior caso, horário de Brasília lido como UTC, a idade
    sai 3 h maior, o que não muda nada num SLA medido em dias.
    """
    if not carregado_em:
        return None
    data = datetime.fromisoformat(carregado_em)
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    idade = (agora or datetime.now(timezone.utc)) - data
    return data, idade.days, idade.total_seconds() <= SLA_DIAS * 86_400

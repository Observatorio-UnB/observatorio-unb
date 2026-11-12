"""Faixas de tempo de formatura do painel.

As faixas vêm prontas da gold (colunas faixa_*_pct, migração 0028) e não se sobrepõem, pela matriz
curricular do curso: mínimo (<= mínimo), ideal (mínimo < t <= ideal), acima do ideal
(ideal < t < máximo) e limite de jubilamento (t >= máximo). Somam 100% dos formados.
"""

FAIXAS = ["Tempo Mínimo", "Tempo Ideal", "Acima do Ideal", "Limite Jubilamento"]
COLUNAS = ["faixa_minimo_pct", "faixa_ideal_pct", "faixa_acima_pct", "faixa_limite_pct"]


def faixas_exclusivas(row) -> list:
    """% dos formados em cada faixa de FAIXAS."""
    return [row[c] for c in COLUNAS]

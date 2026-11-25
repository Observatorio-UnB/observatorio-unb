-- Métricas por curso canônico. As fórmulas são as da camada semântica (macros/metricas.sql), sobre
-- as bases aditivas de int_bases_curso: o mesmo cálculo de metricas_por_recorte, só que no grão do
-- curso. Mesmos números de gold.atualizar_gold (migração 0022), com a qual o fato é reconciliado.
select
    nome_curso,
    ingressantes,
    formados,
    evadidos,
    ativos,
    {{ metrica_taxa_formatura_pct('formados', 'ingressantes') }} as taxa_formatura_pct,
    {{ metrica_taxa_evasao_pct('evadidos', 'ingressantes') }} as taxa_evasao_pct,
    {{ metrica_formados_tempo_ideal_pct('formados_no_ideal', 'formados_com_prazo') }} as formados_tempo_ideal_pct,
    {{ metrica_atraso_medio_semestres('soma_atraso', 'formados_com_atraso') }} as atraso_medio_semestres
from {{ ref('int_bases_curso') }}

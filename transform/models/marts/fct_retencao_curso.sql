-- Grão: um registro por curso canônico, agregando as coortes maduras. O campus é atributo do curso,
-- não parte do grão. Contagens são aditivas entre cursos; taxas, % no tempo ideal, atraso e IRC
-- não são (recalcular a partir das contagens). Só cursos com k >= k_minimo ingressantes.
select
    dc.sk_curso,
    camp.sk_campus,
    m.ingressantes as total_ingressantes,
    m.formados as total_formados,
    m.evadidos as total_evadidos,
    m.ativos as total_ainda_ativos,
    m.taxa_formatura_pct,
    m.taxa_evasao_pct,
    m.formados_tempo_ideal_pct,
    m.atraso_medio_semestres,
    i.indice_retencao_critica,
    i.classificacao_retencao
from {{ ref('int_metricas_curso') }} m
join {{ ref('int_irc_curso') }} i using (nome_curso)
join {{ ref('dim_curso') }} dc using (nome_curso)
join {{ ref('int_campus_do_curso') }} cc using (nome_curso)
join {{ ref('dim_campus') }} camp on camp.campus = cc.campus

-- Tabela de consumo do painel: responde à pergunta da E1, "quais cursos têm a retenção mais
-- crítica e devem ser priorizados para intervenção". Um registro por curso terminal (sem os
-- cursos-tronco, ADR 0022), na ordem do IRC: posicao 1 é o mais crítico.
select
    rank() over (order by f.indice_retencao_critica desc) as posicao,
    c.nome_curso,
    camp.campus,
    c.area_conhecimento,
    c.categoria_grau,
    f.classificacao_retencao,
    f.indice_retencao_critica,
    f.taxa_evasao_pct,
    f.atraso_medio_semestres,
    f.taxa_formatura_pct,
    f.formados_tempo_ideal_pct,
    f.total_ingressantes,
    f.total_formados,
    f.total_evadidos
from {{ ref('fct_retencao_curso') }} f
join {{ ref('dim_curso') }} c using (sk_curso)
join {{ ref('dim_campus') }} camp using (sk_campus)
where not c.is_tronco_abi

-- O fato reconstruído pelo dbt tem de ser igual, curso a curso, ao gold.fato_retencao_curso do
-- pipeline Python (src/db/povoar_dimensional.py), que segue sendo o que o painel lê hoje.
-- Devolve os cursos que só existem de um lado ou que divergem em alguma medida.
with dbt as (
    select c.nome_curso, camp.campus, f.total_ingressantes, f.total_formados, f.total_evadidos,
           f.total_ainda_ativos, f.taxa_formatura_pct, f.taxa_evasao_pct, f.formados_tempo_ideal_pct,
           f.atraso_medio_semestres, f.indice_retencao_critica, f.classificacao_retencao
    from {{ ref('fct_retencao_curso') }} f
    join {{ ref('dim_curso') }} c using (sk_curso)
    join {{ ref('dim_campus') }} camp using (sk_campus)
),

pipeline as (
    select c.nome_curso, camp.campus, f.total_ingressantes, f.total_formados, f.total_evadidos,
           f.total_ainda_ativos, f.taxa_formatura_pct, f.taxa_evasao_pct, f.formados_tempo_ideal_pct,
           f.atraso_medio_semestres, f.indice_retencao_critica, f.classificacao_retencao
    from {{ source('gold', 'fato_retencao_curso') }} f
    join {{ source('gold', 'dim_curso') }} c using (sk_curso)
    join {{ source('gold', 'dim_campus') }} camp using (sk_campus)
)

(select 'so_no_dbt' as diferenca, * from dbt except select 'so_no_dbt', * from pipeline)
union all
(select 'so_no_pipeline', * from pipeline except select 'so_no_pipeline', * from dbt)

-- Índice de Retenção Crítica (ADR 0006): IRC = (0,3 x atraso + 0,7 x evasão) x 100, cada termo
-- saturado nos percentis 5 e 95 e normalizado min-max entre os cursos; classificação pelos quartis.
-- percentile_cont interpola como o quantile do pandas. A fórmula segue a de gold.atualizar_gold
-- (migração 0022) na ordem das operações e no arredondamento (macro arredondar), para dar o mesmo IRC.
with entradas as (
    select
        nome_curso,
        greatest(coalesce(atraso_medio_semestres, 0), 0)::float8 as x_atraso,
        taxa_evasao_pct::float8 as x_evasao
    from {{ ref('int_metricas_curso') }}
),

limites as (
    select
        percentile_cont(0.05) within group (order by x_atraso) as a05,
        percentile_cont(0.95) within group (order by x_atraso) as a95,
        percentile_cont(0.05) within group (order by x_evasao) as e05,
        percentile_cont(0.95) within group (order by x_evasao) as e95
    from entradas
),

saturados as (
    select
        nome_curso,
        least(greatest(x_atraso, a05), a95) as s_atraso,
        least(greatest(x_evasao, e05), e95) as s_evasao
    from entradas, limites
),

irc as (
    select
        nome_curso,
        {{ arredondar(
            "(0.3 * ((s_atraso - min(s_atraso) over ()) / (max(s_atraso) over () - min(s_atraso) over () + 1e-6))"
            ~ " + 0.7 * ((s_evasao - min(s_evasao) over ()) / (max(s_evasao) over () - min(s_evasao) over () + 1e-6)))"
            ~ " * 100", 1) }} as indice_retencao_critica
    from saturados
),

quartis as (
    select
        percentile_cont(0.25) within group (order by indice_retencao_critica) as q25,
        percentile_cont(0.50) within group (order by indice_retencao_critica) as q50,
        percentile_cont(0.75) within group (order by indice_retencao_critica) as q75
    from irc
)

select
    i.nome_curso,
    i.indice_retencao_critica,
    case when i.indice_retencao_critica >= q.q75 then 'RETENÇÃO CRÍTICA'
         when i.indice_retencao_critica >= q.q50 then 'RETENÇÃO ALTA'
         when i.indice_retencao_critica >= q.q25 then 'RETENÇÃO MÉDIA'
         else 'RETENÇÃO BAIXA' end as classificacao_retencao
from irc i
cross join quartis q

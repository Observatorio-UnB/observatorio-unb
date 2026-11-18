-- Distribuição: em cada turma madura, a evasão fica em evasao_por_turma (30% a 60%) e a formatura
-- em formatura_por_turma (35% a 70%), ambos em dbt_project.yml. Na base atual: 40% a 47% e 47% a 57%.
-- Fora disso, o mapeamento da forma de saída para o desfecho quebrou (ex.: evasão virando OUTROS)
-- sem nenhum valor inválido aparecer.
with por_turma as (
    select ano_ingresso,
           100.0 * count(*) filter (where tipo_saida_grupo = 'EVASAO') / count(*) as evasao_pct,
           100.0 * count(*) filter (where tipo_saida_grupo = 'FORMATURA') / count(*) as formatura_pct
    from {{ ref('stg_vinculos') }}
    where ano_ingresso <= (select max(ano_ingresso) - {{ var('anos_maturacao') }} from {{ ref('stg_vinculos') }})
    group by ano_ingresso
)

select ano_ingresso, round(evasao_pct, 1) as evasao_pct, round(formatura_pct, 1) as formatura_pct
from por_turma
where evasao_pct not between {{ var('evasao_por_turma')[0] }} and {{ var('evasao_por_turma')[1] }}
   or formatura_pct not between {{ var('formatura_por_turma')[0] }} and {{ var('formatura_por_turma')[1] }}

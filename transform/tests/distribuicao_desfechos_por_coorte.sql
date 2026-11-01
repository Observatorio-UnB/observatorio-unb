-- Distribuição: em cada coorte madura, a evasão fica entre 30% e 60% dos vínculos e a formatura
-- entre 35% e 70% (na base atual: 40% a 47% e 47% a 57%). Fora disso, o mapeamento da forma de
-- saída para o desfecho quebrou (ex.: evasão virando OUTROS) sem nenhum valor inválido aparecer.
with por_coorte as (
    select ano_ingresso,
           100.0 * count(*) filter (where tipo_saida_grupo = 'EVASAO') / count(*) as evasao_pct,
           100.0 * count(*) filter (where tipo_saida_grupo = 'FORMATURA') / count(*) as formatura_pct
    from {{ ref('stg_vinculos') }}
    where ano_ingresso <= (select max(ano_ingresso) - {{ var('anos_maturacao') }} from {{ ref('stg_vinculos') }})
    group by ano_ingresso
)

select ano_ingresso, round(evasao_pct, 1) as evasao_pct, round(formatura_pct, 1) as formatura_pct
from por_coorte
where evasao_pct not between 30 and 60
   or formatura_pct not between 35 and 70

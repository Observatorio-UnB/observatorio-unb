-- Distribuição: o volume de uma coorte madura não pode variar mais que salto_maximo_entre_coortes
-- (30%, em dbt_project.yml) em relação à anterior. Na base atual (2010 a 2016) a maior variação é de
-- 15%. Um salto maior é carga parcial, partição que não veio ou duplicação: o tipo de erro que deixa o
-- fato plausível e errado.
with por_coorte as (
    select ano_ingresso, count(*) as vinculos
    from {{ ref('stg_vinculos') }}
    where ano_ingresso <= (select max(ano_ingresso) - {{ var('anos_maturacao') }} from {{ ref('stg_vinculos') }})
    group by ano_ingresso
),

com_anterior as (
    select ano_ingresso, vinculos,
           lag(vinculos) over (order by ano_ingresso) as anterior
    from por_coorte
)

select ano_ingresso, anterior, vinculos, round(100.0 * (vinculos - anterior) / anterior, 1) as variacao_pct
from com_anterior
where anterior is not null
  and abs(vinculos - anterior) > {{ var('salto_maximo_entre_coortes') }} * anterior

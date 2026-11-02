-- Vínculos das coortes maduras: ingresso até o último ano da base menos anos_maturacao (ADR 0014),
-- com o prazo ideal da matriz do vínculo.
with corte as (
    select max(ano_ingresso) - {{ var('anos_maturacao') }} as ultimo_ano
    from {{ ref('stg_vinculos') }}
)

select
    e.nome_curso,
    v.tipo_saida_grupo,
    v.semestres_permanencia_valida,
    e.semestre_ideal
from {{ ref('stg_vinculos') }} v
join {{ ref('stg_estruturas_curriculares') }} e using (id_estrutura)
where v.ano_ingresso <= (select ultimo_ano from corte)

-- Turno de cada curso canônico, com a regra da gold (migração 0022, gold.turno_grupo): matutino e
-- vespertino viram DIURNO; mais de um turno entre as ofertas do nome vira "DIURNO E NOTURNO"; sem
-- turno informado, DIURNO.
with turnos as (
    select distinct
        nome_curso,
        case when turno like '%NOTURNO%' then 'NOTURNO'
             when turno like '%INTEGRAL%' then 'INTEGRAL'
             else 'DIURNO' end as turno
    from {{ ref('stg_cursos') }}
    where turno is not null
)

select
    e.nome_curso,
    coalesce(string_agg(distinct t.turno, ' E ' order by t.turno), 'DIURNO') as turno
from {{ ref('stg_estruturas_curriculares') }} e
left join turnos t on t.nome_curso = e.nome_curso
group by e.nome_curso

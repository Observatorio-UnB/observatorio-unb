-- Atributos de cada curso canônico, com as regras de src/pipeline/build_gold.py: valem os da oferta
-- principal do nome (catálogo vigente, menor id_curso), e bacharelado + licenciatura com o mesmo
-- nome vira MISTO (ADR 0004). Sem oferta com o nome (ex.: COMUNICACAO SOCIAL), valem os do curso
-- dono da matriz.
with principal as (
    select distinct on (nome_curso) *
    from {{ ref('stg_cursos') }}
    order by nome_curso, no_catalogo_vigente desc, id_curso
),

misto as (
    select nome_curso
    from {{ ref('stg_cursos') }}
    group by nome_curso
    having count(distinct categoria_grau) > 1
)

select
    e.nome_curso,
    e.id_curso_dono as id_curso_origem,
    case when m.nome_curso is not null then 'MISTO (BACHARELADO + LICENCIATURA)'
         else coalesce(p.grau_academico, dono.grau_academico) end as grau_academico,
    case when m.nome_curso is not null then 'MISTO'
         else coalesce(p.categoria_grau, dono.categoria_grau) end as categoria_grau,
    coalesce(p.area_conhecimento, dono.area_conhecimento) as area_conhecimento,
    coalesce(p.departamento, dono.departamento) as departamento,
    coalesce(p.is_tronco_abi, dono.is_tronco_abi) as is_tronco_abi
from {{ ref('stg_estruturas_curriculares') }} e
join {{ ref('stg_cursos') }} dono on dono.id_curso = e.id_curso_dono
left join principal p on p.nome_curso = e.nome_curso
left join misto m on m.nome_curso = e.nome_curso

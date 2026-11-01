-- Campus de cada curso canônico: MULTICAMPUS quando o nome é oferecido em mais de um campus
-- (ADR 0021); sem oferta com o nome, o campus do curso dono da matriz.
select
    e.nome_curso,
    case when count(distinct o.campus) > 1 then 'MULTICAMPUS'
         else coalesce(min(o.campus), dono.campus) end as campus
from {{ ref('stg_estruturas_curriculares') }} e
join {{ ref('stg_cursos') }} dono on dono.id_curso = e.id_curso_dono
left join {{ ref('stg_cursos') }} o on o.nome_curso = e.nome_curso
group by e.nome_curso, dono.campus

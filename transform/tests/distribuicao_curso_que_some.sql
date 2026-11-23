-- Distribuição: curso que some numa coorte. Curso com ingressantes_curso_que_some (80, em
-- dbt_project.yml) ou mais ingressantes na coorte anterior e na seguinte não pode ter zero na do meio.
-- Cursos com entrada alternada existem (Educação do Campo pula anos com 56 a 66 ingressantes ao lado),
-- por isso o limite. O que se quer pegar é o curso grande que perdeu a matriz na harmonização e saiu
-- da série sem erro. Ponto cego: curso menor que o limite pode sumir sem ser acusado.
with por_curso as (
    select e.nome_curso, v.ano_ingresso, count(*) as ingressantes
    from {{ ref('stg_vinculos') }} v
    join {{ ref('stg_estruturas_curriculares') }} e using (id_estrutura)
    group by e.nome_curso, v.ano_ingresso
),

anos as (
    -- a última coorte pode estar incompleta: fica de fora como coorte do meio e como vizinha
    select generate_series(min(ano_ingresso) + 1, max(ano_ingresso) - 2) as ano
    from {{ ref('stg_vinculos') }}
)

select antes.nome_curso, a.ano as ano_sem_ingresso, antes.ingressantes as antes, depois.ingressantes as depois
from anos a
join por_curso antes on antes.ano_ingresso = a.ano - 1 and antes.ingressantes >= {{ var('ingressantes_curso_que_some') }}
join por_curso depois on depois.nome_curso = antes.nome_curso and depois.ano_ingresso = a.ano + 1
                      and depois.ingressantes >= {{ var('ingressantes_curso_que_some') }}
where not exists (
    select 1 from por_curso p where p.nome_curso = antes.nome_curso and p.ano_ingresso = a.ano
)

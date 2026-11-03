-- Dimensão de campus, com MULTICAMPUS para os cursos oferecidos em mais de um.
select
    md5(campus) as sk_campus,
    campus,
    case campus
        when 'DARCY RIBEIRO' then 'Plano Piloto'
        when 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM ENGENHARIA (FCTE)' then 'Gama'
        when 'FACULDADE DE CIENCIAS E TECNOLOGIAS EM SAUDE (FCTS)' then 'Ceilândia'
        when 'FACULDADE DE PLANALTINA (FUP)' then 'Planaltina'
        else 'Distrito Federal'
    end as regiao_admin
from (
    select campus from {{ ref('stg_cursos') }}
    union
    select 'MULTICAMPUS'
) c

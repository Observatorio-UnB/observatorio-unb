-- Uma linha por oferta do catálogo de cursos (id_curso).
select
    id_curso,
    nome_curso_norm as nome_curso,
    campus,
    turno,
    grau_academico,
    categoria_grau,
    area_conhecimento,
    departamento,
    is_tronco_abi,
    ativo as no_catalogo_vigente
from {{ source('silver', 'cursos') }}

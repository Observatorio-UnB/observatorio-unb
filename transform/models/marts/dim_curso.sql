-- Dimensão de cursos: uma linha por curso canônico. A chave substituta é o hash do nome, estável
-- entre execuções e entre bancos: o mesmo curso tem a mesma sk_curso em qualquer reconstrução.
select
    md5(nome_curso) as sk_curso,
    nome_curso,
    id_curso_origem,
    grau_academico,
    categoria_grau,
    area_conhecimento,
    departamento,
    is_tronco_abi
from {{ ref('int_atributos_curso') }}

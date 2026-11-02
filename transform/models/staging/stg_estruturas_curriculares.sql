-- Uma matriz por curso canônico: o nome que a harmonização (ADR 0003) dá ao curso em todas as fontes.
select
    id_estrutura,
    id_curso as id_curso_dono,
    nome_curso_canonico as nome_curso,
    semestre_minimo,
    semestre_ideal,
    semestre_maximo
from {{ source('silver', 'estruturas_curriculares') }}

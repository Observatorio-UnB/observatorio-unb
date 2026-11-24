-- Bases aditivas de cada curso canônico: contagens e somas que se podem somar entre cursos. As
-- métricas (taxas, médias) não se somam: cada recorte as recalcula destas bases, pelas macros de
-- macros/metricas.sql. Só cursos com k >= k_minimo ingressantes (ADR 0005).
select
    nome_curso,
    count(*) as ingressantes,
    count(*) filter (where tipo_saida_grupo = 'FORMATURA') as formados,
    count(*) filter (where tipo_saida_grupo = 'EVASAO') as evadidos,
    count(*) filter (where tipo_saida_grupo = 'ATIVO') as ativos,
    -- Formados com permanência calculável: base do % no prazo ideal e do tempo médio.
    count(semestres_permanencia_valida) filter (where tipo_saida_grupo = 'FORMATURA') as formados_com_prazo,
    count(*) filter (where tipo_saida_grupo = 'FORMATURA'
                       and semestres_permanencia_valida <= semestre_ideal) as formados_no_ideal,
    sum(semestres_permanencia_valida) filter (where tipo_saida_grupo = 'FORMATURA') as soma_permanencia,
    -- Formados com permanência e prazo ideal: base do atraso médio e do prazo ideal médio.
    count(semestres_permanencia_valida - semestre_ideal)
        filter (where tipo_saida_grupo = 'FORMATURA') as formados_com_atraso,
    sum(semestres_permanencia_valida - semestre_ideal)
        filter (where tipo_saida_grupo = 'FORMATURA') as soma_atraso,
    sum(semestre_ideal) filter (where tipo_saida_grupo = 'FORMATURA'
                                  and semestres_permanencia_valida is not null) as soma_prazo_ideal
from {{ ref('int_coortes_maduras') }}
group by nome_curso
having count(*) >= {{ var('k_minimo') }}

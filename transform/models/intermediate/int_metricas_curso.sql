-- Contagens e taxas por curso canônico, só com k >= k_minimo ingressantes (ADR 0005).
-- % no tempo ideal e atraso médio só sobre formados com permanência calculável.
-- Mesmas fórmulas e mesmo arredondamento de gold.atualizar_gold (migração 0022): a razão em ponto
-- flutuante vezes 100 e a macro arredondar, para o fato reconciliar com a gold também nos empates.
with contagens as (
    select
        nome_curso,
        count(*) as ingressantes,
        count(*) filter (where tipo_saida_grupo = 'FORMATURA') as formados,
        count(*) filter (where tipo_saida_grupo = 'EVASAO') as evadidos,
        count(*) filter (where tipo_saida_grupo = 'ATIVO') as ativos,
        count(semestres_permanencia_valida) filter (where tipo_saida_grupo = 'FORMATURA') as formados_com_prazo,
        count(*) filter (where tipo_saida_grupo = 'FORMATURA'
                           and semestres_permanencia_valida <= semestre_ideal) as formados_no_ideal,
        avg(semestres_permanencia_valida - semestre_ideal)
            filter (where tipo_saida_grupo = 'FORMATURA') as atraso
    from {{ ref('int_coortes_maduras') }}
    group by nome_curso
    having count(*) >= {{ var('k_minimo') }}
)

select
    nome_curso,
    ingressantes,
    formados,
    evadidos,
    ativos,
    {{ arredondar("formados::double precision / ingressantes * 100", 2) }} as taxa_formatura_pct,
    {{ arredondar("evadidos::double precision / ingressantes * 100", 2) }} as taxa_evasao_pct,
    case when formados_com_prazo > 0
         then {{ arredondar("formados_no_ideal::double precision / formados_com_prazo * 100", 2) }}
         else 0 end as formados_tempo_ideal_pct,
    {{ arredondar("atraso", 2) }} as atraso_medio_semestres
from contagens

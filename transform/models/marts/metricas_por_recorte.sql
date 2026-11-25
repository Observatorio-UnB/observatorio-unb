-- Camada semântica, recortes acima do curso: cada métrica da UnB inteira e por campus, grau, área e
-- turno. É daqui que o painel tira as comparações entre grupos de cursos, em vez de tirar a média das
-- taxas dos cursos (o que dá peso igual a um curso de 20 e a um de 2.000 ingressantes).
--
-- Universo: os cursos terminais publicados no ranking (painel_cursos_criticos), isto é, com
-- k >= k_minimo e sem os cursos-tronco (ADR 0022). Somando as bases aditivas desses cursos e
-- aplicando as macros de macros/metricas.sql, o recorte tem a mesma definição do curso.
-- O IRC não entra: é relativo entre cursos (normalizado min-max) e não existe para um grupo.
with cursos as (
    select
        b.*,
        coalesce(cc.campus, 'NÃO INFORMADO') as campus,
        coalesce(a.categoria_grau, 'NÃO INFORMADO') as categoria_grau,
        coalesce(a.area_conhecimento, 'NÃO INFORMADO') as area_conhecimento,
        coalesce(t.turno, 'DIURNO') as turno
    from {{ ref('int_bases_curso') }} b
    join {{ ref('int_atributos_curso') }} a using (nome_curso)
    left join {{ ref('int_campus_do_curso') }} cc using (nome_curso)
    left join {{ ref('int_turno_do_curso') }} t using (nome_curso)
    where not coalesce(a.is_tronco_abi, false)
),

recortes as (
    select 'UNB' as recorte, 'UNB' as valor, cursos.* from cursos
    union all select 'CAMPUS', campus, cursos.* from cursos
    union all select 'CATEGORIA_GRAU', categoria_grau, cursos.* from cursos
    union all select 'AREA_CONHECIMENTO', area_conhecimento, cursos.* from cursos
    union all select 'TURNO', turno, cursos.* from cursos
),

somado as (
    select
        recorte,
        valor,
        count(*) as cursos,
        sum(ingressantes) as ingressantes,
        sum(formados) as formados,
        sum(evadidos) as evadidos,
        sum(ativos) as ativos,
        sum(formados_com_prazo) as formados_com_prazo,
        sum(formados_no_ideal) as formados_no_ideal,
        sum(soma_permanencia) as soma_permanencia,
        sum(formados_com_atraso) as formados_com_atraso,
        sum(soma_atraso) as soma_atraso,
        sum(soma_prazo_ideal) as soma_prazo_ideal
    from recortes
    group by recorte, valor
)

select
    recorte,
    valor,
    cursos,
    ingressantes::bigint as ingressantes,
    formados::bigint as formados,
    evadidos::bigint as evadidos,
    ativos::bigint as ativos,
    {{ metrica_taxa_formatura_pct('formados', 'ingressantes') }} as taxa_formatura_pct,
    {{ metrica_taxa_evasao_pct('evadidos', 'ingressantes') }} as taxa_evasao_pct,
    {{ metrica_formados_tempo_ideal_pct('formados_no_ideal', 'formados_com_prazo') }} as formados_tempo_ideal_pct,
    {{ metrica_atraso_medio_semestres('soma_atraso', 'formados_com_atraso') }} as atraso_medio_semestres,
    {{ metrica_tempo_medio_formatura_semestres('soma_permanencia', 'formados_com_prazo') }} as tempo_medio_formatura_semestres,
    {{ metrica_prazo_ideal_medio_semestres('soma_prazo_ideal', 'formados_com_atraso') }} as prazo_ideal_medio_semestres
from somado

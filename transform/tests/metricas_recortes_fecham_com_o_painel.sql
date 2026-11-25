-- A camada semântica não pode dar dois números para a mesma coisa. Confere que:
--   1. o recorte UNB tem os mesmos cursos e as mesmas contagens que o ranking do painel
--      (painel_cursos_criticos), que é o universo declarado dos recortes;
--   2. cada recorte (campus, grau, área, turno) particiona esse universo: somando os grupos de um
--      recorte, voltam os mesmos cursos e ingressantes da UnB;
--   3. no grão do curso, as taxas do painel são as que as macros da camada semântica dão a partir das
--      contagens do próprio painel (ninguém recalculou a taxa por fora).
with painel as (
    select count(*) as cursos, sum(total_ingressantes) as ingressantes,
           sum(total_formados) as formados, sum(total_evadidos) as evadidos
    from {{ ref('painel_cursos_criticos') }}
),

unb as (
    select cursos, ingressantes, formados, evadidos
    from {{ ref('metricas_por_recorte') }}
    where recorte = 'UNB'
),

por_recorte as (
    select recorte, sum(cursos) as cursos, sum(ingressantes) as ingressantes
    from {{ ref('metricas_por_recorte') }}
    group by recorte
)

select 'unb_diferente_do_painel' as problema, null::text as detalhe
from painel, unb
where (painel.cursos, painel.ingressantes, painel.formados, painel.evadidos)
      is distinct from (unb.cursos, unb.ingressantes, unb.formados, unb.evadidos)

union all

select 'recorte_nao_particiona', r.recorte
from por_recorte r, unb
where (r.cursos, r.ingressantes) is distinct from (unb.cursos, unb.ingressantes)

union all

select 'taxa_do_painel_fora_da_definicao', p.nome_curso
from {{ ref('painel_cursos_criticos') }} p
where p.taxa_evasao_pct is distinct from {{ metrica_taxa_evasao_pct('p.total_evadidos', 'p.total_ingressantes') }}
   or p.taxa_formatura_pct is distinct from {{ metrica_taxa_formatura_pct('p.total_formados', 'p.total_ingressantes') }}

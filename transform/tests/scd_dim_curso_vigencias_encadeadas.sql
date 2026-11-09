-- SCD tipo 2: as versões de um curso se encadeiam sem buraco nem sobreposição. Cada versão fechada
-- termina depois de começar e exatamente onde a seguinte começa; a primeira começa em 1962. Uma
-- sobrescrita, ou uma versão apagada, quebra a cadeia e reescreve a série retroativamente.
with versoes as (
    select
        nome_curso,
        vigente_de,
        vigente_ate,
        lead(vigente_de) over (partition by nome_curso order by vigente_de) as proxima_de,
        row_number() over (partition by nome_curso order by vigente_de) as ordem
    from {{ ref('dim_curso') }}
)

select *
from versoes
where (ordem = 1 and vigente_de <> timestamp '1962-04-21 00:00:00')
   or (vigente_ate is not null and vigente_ate <= vigente_de)
   or (vigente_ate is distinct from proxima_de)

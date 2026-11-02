-- Distribuição: a mediana da taxa de evasão entre os cursos do fato fica entre 30% e 60% (44,2% na
-- base atual). Um deslocamento da mediana inteira é erro de regra, não de um curso.
select percentile_cont(0.5) within group (order by taxa_evasao_pct) as mediana
from {{ ref('fct_retencao_curso') }}
having percentile_cont(0.5) within group (order by taxa_evasao_pct) not between 30 and 60

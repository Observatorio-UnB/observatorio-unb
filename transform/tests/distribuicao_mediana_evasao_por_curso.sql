-- Distribuição: a mediana da taxa de evasão entre os cursos do fato fica em mediana_evasao_por_curso
-- (30% a 60%, em dbt_project.yml; 44,2% na base atual). Um deslocamento da mediana inteira é erro de
-- regra, não de um curso.
select percentile_cont(0.5) within group (order by taxa_evasao_pct) as mediana
from {{ ref('fct_retencao_curso') }}
having percentile_cont(0.5) within group (order by taxa_evasao_pct) not between {{ var('mediana_evasao_por_curso')[0] }} and {{ var('mediana_evasao_por_curso')[1] }}

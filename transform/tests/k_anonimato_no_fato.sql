-- Nenhum curso com menos de k_minimo ingressantes pode chegar à camada de consumo (ADR 0005).
select sk_curso, total_ingressantes
from {{ ref('fct_retencao_curso') }}
where total_ingressantes < {{ var('k_minimo') }}

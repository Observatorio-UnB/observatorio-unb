-- Domínio: formados, evadidos e ativos são partes dos ingressantes e não podem somar mais que eles,
-- nem ser negativos. A soma estourada é contagem dupla na junção.
select sk_curso, total_ingressantes, total_formados, total_evadidos, total_ainda_ativos
from {{ ref('fct_retencao_curso') }}
where total_formados + total_evadidos + total_ainda_ativos > total_ingressantes
   or least(total_formados, total_evadidos, total_ainda_ativos) < 0

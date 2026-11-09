-- O fato é recriado a cada execução e tem de apontar para a versão atual do curso. Apontar para uma
-- versão fechada mostraria no painel a classificação antiga (área, grau, tronco ABI).
select f.sk_curso, c.nome_curso, c.vigente_de, c.vigente_ate
from {{ ref('fct_retencao_curso') }} f
join {{ ref('dim_curso') }} c using (sk_curso)
where not c.is_atual

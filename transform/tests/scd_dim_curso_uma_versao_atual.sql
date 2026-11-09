-- SCD tipo 2: cada curso tem exatamente uma versão atual, e só a versão aberta (vigente_ate nulo) é
-- a atual. Duas versões atuais duplicariam o curso no fato; nenhuma o tiraria do painel.
select nome_curso, count(*) filter (where is_atual) as versoes_atuais
from {{ ref('dim_curso') }}
group by nome_curso
having count(*) filter (where is_atual) <> 1
    or bool_or(is_atual <> (vigente_ate is null))

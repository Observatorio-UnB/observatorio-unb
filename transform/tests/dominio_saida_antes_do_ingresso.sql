-- Domínio: ninguém sai antes de entrar. A exceção conhecida é o período de saída estimado pela data
-- do diploma no SIGAA (ADR 0015), que gera 9 casos na base atual e fica no teste de aviso ao lado.
-- Saída antes do ingresso com período publicado pela fonte é erro.
select id_vinculo, ano_ingresso, ano_saida, fonte
from {{ ref('stg_vinculos') }}
where ano_saida < ano_ingresso
  and not periodo_saida_estimado

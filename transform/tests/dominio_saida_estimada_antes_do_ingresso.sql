-- Aviso: saída estimada (ADR 0015) antes do ingresso. São 9 na base atual, todas de ingressantes de
-- 2023 e 2024 com diploma registrado no ano anterior. Vira erro se passar de 50, sinal de que a
-- estimativa mudou de comportamento.
{{ config(severity='error', warn_if='>0', error_if='>50') }}
select id_vinculo, ano_ingresso, ano_saida
from {{ ref('stg_vinculos') }}
where ano_saida < ano_ingresso
  and periodo_saida_estimado

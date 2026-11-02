-- O esquema de cada camada é o nome configurado (dbt_staging, dbt_intermediate, dbt_marts), e não
-- o padrão do dbt, que prefixaria o esquema do perfil (dbt_marts_dbt_staging). O prefixo_esquema
-- isola uma execução de teste (inj_dbt_staging, ...) das camadas de verdade.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ var('prefixo_esquema', '') }}{{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}

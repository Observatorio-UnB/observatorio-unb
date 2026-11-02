-- O esquema de cada camada é o nome configurado (dbt_staging, dbt_intermediate, dbt_marts), e não
-- o padrão do dbt, que prefixaria o esquema do perfil (dbt_marts_dbt_staging).
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}

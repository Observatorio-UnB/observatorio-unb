-- Toda métrica publicada pela camada semântica tem definição versionada no registro
-- (seeds/metricas_definicoes.csv), e toda definição do registro é publicada. Devolve as que sobram
-- de um lado ou do outro.
-- depends_on: {{ ref('metricas_por_recorte') }}
{%- set publicadas = [] -%}
{%- if execute -%}
    {%- for coluna in adapter.get_columns_in_relation(ref('metricas_por_recorte')) -%}
        {%- if coluna.name not in ['recorte', 'valor', 'cursos'] -%}
            {%- do publicadas.append(coluna.name) -%}
        {%- endif -%}
    {%- endfor -%}
{%- endif -%}
-- Só no grão do curso (relativas entre cursos): publicadas no fato e no painel.
{%- do publicadas.extend(['indice_retencao_critica', 'classificacao_retencao']) %}

with publicadas as (
    select unnest(array[{% for m in publicadas %}'{{ m }}'{{ ',' if not loop.last }}{% endfor %}]::text[]) as metrica
),

registro as (
    select metrica from {{ ref('metricas_definicoes') }}
)

(select 'publicada_sem_definicao' as problema, metrica from publicadas
 except select 'publicada_sem_definicao', metrica from registro)
union all
(select 'definicao_sem_publicacao', metrica from registro
 except select 'definicao_sem_publicacao', metrica from publicadas)
